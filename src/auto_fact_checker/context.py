"""RunContext: the single choke point every LLM call of a run goes through.

Local: turns (step, prompt, label) into an LLMRequest from the step's StepConfig, enforces the global spend cap and
the per-run budget, honours the Stop button, logs the full prompt and output, writes per-call artifact files,
records spend and call bookkeeping.
Global context: phases/*.py only ever call ctx.call(); pipeline.py opens one RunContext per batch of work on a
FactCheckRun (a run can receive several batches: iterations, "One more iteration", perspective buttons).
"""

import itertools
import json
import re
import threading

from . import spend
from .backends import LLMRequest, LLMResult, call_llm
from .config import FactCheckConfig, Settings, backend_for, get_settings
from .logs import attach_run_log, detach_run_log, log_block, run_logger
from .results import FactCheckRun, record_call, save_run


class Cancelled(RuntimeError):
    """Raised when the user pressed Stop."""


_HANDLERS: dict[str, list] = {}  # run_id -> [handler, refcount]; one run.log handler however many contexts
_H_LOCK = threading.Lock()
CANCEL: dict[str, threading.Event] = {}  # run_id -> Stop flag shared by all contexts of the run


class RunContext:
    """Per-batch execution context bound to one FactCheckRun and one FactCheckConfig."""

    def __init__(self, run: FactCheckRun, cfg: FactCheckConfig, settings: Settings | None = None):
        self.run, self.cfg = run, cfg
        self.settings = settings or get_settings()
        self.dir = self.settings.runs_dir / run.run_id
        self.log = run_logger(run.run_id, "afc.pipeline")
        self.cancel = CANCEL.setdefault(run.run_id, threading.Event())
        self.cancel.clear()  # a new batch starts un-cancelled
        self._counter = itertools.count(len(run.calls) + 1)  # artifact numbering continues across batches
        with _H_LOCK:
            entry = _HANDLERS.get(run.run_id)
            if entry:
                entry[1] += 1
            else:
                _HANDLERS[run.run_id] = [attach_run_log(self.dir / "run.log", run.run_id), 1]

    def request(self, step: str, prompt: str, label: str, agents: dict | None = None) -> LLMRequest:
        """LLMRequest from the step's settings; Claude Code also gets the remaining budget as --max-budget-usd."""
        sc = self.cfg.steps[step]
        backend = backend_for(sc)
        remaining = min(self.cfg.max_cost_usd - self.run.total_cost_usd,
                        self.settings.spend_limit_usd - spend.total_billed(self.settings.ledger))
        return LLMRequest(backend=backend, model=sc.model, prompt=prompt, label=label, effort=sc.effort,
                          web_search=sc.web_search, search_context_size=sc.search_context_size,
                          max_searches=sc.max_searches, blocked_domains=sc.blocked_domains,
                          allow_subagents=sc.allow_subagents, agents=agents, max_turns=sc.max_turns,
                          max_budget_usd=round(max(remaining, 0.01), 4) if backend == "claude_code" else None,
                          timeout_s=sc.timeout_s, cancel=self.cancel)

    def call(self, step: str, prompt: str, label: str, agents: dict | None = None) -> LLMResult:
        """Run one LLM call with logging, artifacts, budget checks and spend recording."""
        if self.cancel.is_set():
            raise Cancelled("stopped by user")
        spend.check_budget(self.settings.ledger, self.settings.spend_limit_usd)  # global cap (logs/spend.jsonl)
        if self.run.total_cost_usd >= self.cfg.max_cost_usd:
            raise spend.BudgetExceeded(f"per-run budget max_cost_usd=${self.cfg.max_cost_usd} reached")
        req = self.request(step, prompt, label, agents)
        n = next(self._counter)
        stem = self.dir / "calls" / f"{n:03d}_{re.sub(r'[^A-Za-z0-9_.-]+', '_', label)}"
        stem.parent.mkdir(parents=True, exist_ok=True)
        stem.with_suffix(".prompt.md").write_text(prompt, encoding="utf-8")
        if agents:  # subagent definitions passed to `claude --agents`
            stem.with_suffix(".agents.json").write_text(json.dumps(agents, indent=1, ensure_ascii=False),
                                                        encoding="utf-8")
            log_block(self.log, f"AGENTS #{n} {label}", json.dumps(agents, indent=1, ensure_ascii=False))
        log_block(self.log, f"PROMPT #{n} {label} [{req.backend}/{req.model}, search={req.web_search}]", prompt)
        try:
            res = call_llm(req, self.log)
        except Exception as e:  # network/auth/CLI errors become a failed result instead of crashing the run
            self.log.exception("Call %s failed", label)
            res = LLMResult(backend=req.backend, model=req.model, error=f"{type(e).__name__}: {e}")
        log_block(self.log, f"OUTPUT #{n} {label}", res.text)
        self.log.info("CALL #%d %s: %s/%s tokens in=%d out=%d searches=%d cost=%s billed=%s %.1fs error=%s "
                      "sources=%s", n, label, res.backend, res.model, res.input_tokens, res.output_tokens,
                      res.web_searches, f"${res.cost_usd:.5f}" if res.cost_usd is not None else "unknown",
                      res.billed, res.duration_s, res.error, res.sources)
        stem.with_suffix(".output.md").write_text(res.text, encoding="utf-8")
        stem.with_suffix(".result.json").write_text(res.model_dump_json(indent=1), encoding="utf-8")
        spend.record(self.settings.ledger, res.cost_usd, res.billed, label, run_id=self.run.run_id,
                     backend=res.backend, model=res.model, searches=res.web_searches)
        record_call(self.run, step, label, res)
        if self.cancel.is_set():
            raise Cancelled("stopped by user")
        return res

    def save(self) -> None:
        """Persist the run record (after each iteration and at the end)."""
        save_run(self.run, self.settings.runs_dir)

    def close(self) -> None:
        """Save the run and release this context's share of the run.log handler."""
        self.save()
        with _H_LOCK:
            entry = _HANDLERS.get(self.run.run_id)
            if entry:
                entry[1] -= 1
                if entry[1] == 0:
                    detach_run_log(entry[0])
                    del _HANDLERS[self.run.run_id]


def stop_run(run_id: str) -> None:
    """Signal Stop to every running call of a run (CLI agents are killed by their watchdog)."""
    CANCEL.setdefault(run_id, threading.Event()).set()
