"""Run records: per-call results, per-iteration results and the whole fact-checking run.

Local: pydantic models that serialise to runs/<run_id>/run.json, plus an in-memory RUNS store.
Global context: pipeline.py appends to a FactCheckRun while it works; the Gradio UI polls RUNS[run_id] to render
progress (iterations, perspectives, costs) and the "One more iteration" button continues the same run object.
"""

import re
import threading
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from .backends.base import LLMResult
from .config import FactCheckConfig
from .schema import FactCheckSummary


class CheckResult(BaseModel):
    """Outcome of one check / perspective / synthesis call on a target (whole text or one claim)."""

    label: str  # call label, e.g. "iter1/check/claim2"
    step: str  # check | perspective | synthesize | merge
    target: str  # the text that was evaluated
    persona: str | None = None  # scientist for perspective calls
    report: str = ""  # full answer (markdown report + JSON block)
    summary: FactCheckSummary | None = None  # parsed JSON block (None if unparseable even after repair)


class CallRecord(BaseModel):
    """Bookkeeping for one LLM call (shown in the UI's cost table)."""

    label: str
    step: str
    backend: str
    model: str
    cost_usd: float | None
    billed: bool
    web_searches: int
    input_tokens: int
    output_tokens: int
    duration_s: float
    error: str | None = None


class IterationResult(BaseModel):
    """One pass over the text: the final merged result plus every intermediate result."""

    index: int
    input_text: str
    claims: list[str] = []  # extracted claims (separate_call_per_claim strategy)
    parts: list[CheckResult] = []  # per-claim / per-scientist results and per-claim syntheses
    final: CheckResult | None = None


class FactCheckRun(BaseModel):
    """A whole run: original text, configuration, iterations, ad-hoc perspective calls, calls and status."""

    run_id: str
    created: str
    original_text: str
    config: FactCheckConfig
    iterations: list[IterationResult] = []
    perspectives: list[CheckResult] = []  # disconnected per-scientist calls triggered from the UI
    calls: list[CallRecord] = []
    status: str = "created"  # created | running | done | stopped | error
    stop_reason: str | None = None

    @property
    def current_text(self) -> str:
        """Text the next iteration checks: the latest corrected text, else the latest input (or the original)."""
        for it in reversed(self.iterations):
            if it.final and it.final.summary and (it.final.summary.corrected_text or "").strip():
                return it.final.summary.corrected_text.strip()
        return self.iterations[-1].input_text if self.iterations else self.original_text

    @property
    def total_cost_usd(self) -> float:
        """Sum of known per-call costs (billed and notional)."""
        return sum(c.cost_usd or 0.0 for c in self.calls)

    @property
    def billed_cost_usd(self) -> float:
        """Sum of costs that were actually billed to an API key."""
        return sum(c.cost_usd or 0.0 for c in self.calls if c.billed)


RUNS: dict[str, FactCheckRun] = {}  # in-memory store polled by the UI
_RUNS_LOCK = threading.Lock()


def new_run(text: str, cfg: FactCheckConfig) -> FactCheckRun:
    """Create and register a run with a sortable, readable id like 20261017_131500_123456_gpt-3-has-175b."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())[:24].strip("-") or "text"
    now = datetime.now()
    run = FactCheckRun(run_id=f"{now:%Y%m%d_%H%M%S_%f}_{slug}", created=now.isoformat(timespec="seconds"),
                       original_text=text, config=cfg)
    with _RUNS_LOCK:
        RUNS[run.run_id] = run
    return run


def save_run(run: FactCheckRun, runs_dir: Path) -> Path:
    """Write runs/<run_id>/run.json (full record, re-loadable with FactCheckRun.model_validate_json)."""
    path = runs_dir / run.run_id / "run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(run.model_dump_json(indent=1), encoding="utf-8")
    return path


def record_call(run: FactCheckRun, step: str, label: str, res: LLMResult) -> None:
    """Append a CallRecord (thread-safe: parallel per-claim calls finish concurrently)."""
    rec = CallRecord(label=label, step=step, backend=res.backend, model=res.model, cost_usd=res.cost_usd,
                     billed=res.billed, web_searches=res.web_searches, input_tokens=res.input_tokens,
                     output_tokens=res.output_tokens, duration_s=round(res.duration_s, 2), error=res.error)
    with _RUNS_LOCK:
        run.calls.append(rec)


