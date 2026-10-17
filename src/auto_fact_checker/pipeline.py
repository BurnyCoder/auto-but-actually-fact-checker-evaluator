"""THE wrapper: runs a fact-check as a sequence of clearly named phases.

Read top to bottom:
  run_fact_check   -> for each iteration: run_iteration, then iterate.should_stop
  run_iteration    -> extract_claims (per-claim strategy) -> check every (claim x scientist) target in parallel
                      -> synthesize per claim -> synthesize the whole text
  run_perspective  -> one disconnected per-scientist call (UI buttons)
  synthesize_perspectives -> merge those perspective calls
Global context: the UI (ui.py), the CLI (__main__.py) and the benchmark (bench/run.py) only call these functions;
every LLM call inside goes through context.RunContext.call().
"""

from concurrent.futures import ThreadPoolExecutor

from .config import FactCheckConfig
from .context import Cancelled, RunContext
from .phases.check import check
from .phases.extract import extract_claims
from .phases.iterate import should_stop
from .phases.synthesize import synthesize
from .results import CheckResult, FactCheckRun, IterationResult, new_run
from .spend import BudgetExceeded


def run_fact_check(text: str, cfg: FactCheckConfig, run: FactCheckRun | None = None,
                   max_new_iterations: int | None = None) -> FactCheckRun:
    """Fact-check `text` (new run) or continue `run`; max_new_iterations=1 implements "One more iteration"."""
    run = run or new_run(text, cfg)
    run.config, run.status, run.stop_reason = cfg, "running", None
    ctx = RunContext(run, cfg)
    budget = max_new_iterations or (cfg.max_iterations if cfg.iterate_until_accurate else 1)
    ctx.log.info("Run %s: %d iteration(s) max, claim_strategy=%s, scientist_strategy=%s", run.run_id, budget,
                 cfg.claim_strategy, cfg.scientist_strategy)
    try:
        for _ in range(budget):
            run.iterations.append(IterationResult(index=len(run.iterations) + 1, input_text=run.current_text))
            run_iteration(run.iterations[-1], cfg, ctx)
            ctx.save()
            run.stop_reason = should_stop(run, cfg)
            ctx.log.info("Iteration %d done: accuracy=%s stop_reason=%s", run.iterations[-1].index,
                         _accuracy(run.iterations[-1].final), run.stop_reason)
            if run.stop_reason and max_new_iterations is None:
                break
        run.status = "done"
    except (BudgetExceeded, Cancelled) as e:
        run.status, run.stop_reason = "stopped", str(e)
        ctx.log.warning("Run %s stopped: %s", run.run_id, e)
    except Exception as e:
        run.status, run.stop_reason = "error", f"{type(e).__name__}: {e}"
        ctx.log.exception("Run %s failed", run.run_id)
    finally:
        ctx.close()
    return run


def run_iteration(it: IterationResult, cfg: FactCheckConfig, ctx: RunContext) -> IterationResult:
    """One pass: targets = whole text or extracted claims; jobs = general check and/or one call per scientist."""
    p = f"iter{it.index}"
    if cfg.claim_strategy == "separate_call_per_claim":
        it.claims = [c.claim for c in extract_claims(it.input_text, cfg, ctx, f"{p}/extract")]
        targets = [(claim, it.input_text) for claim in it.claims]  # each claim keeps the document as context
    else:
        targets = [(it.input_text, None)]  # whole text; subagent strategies split it inside the agent
    personas = cfg.perspective_scientists if cfg.scientist_strategy == "separate_call_per_scientist" else []
    jobs = [(i, target, context, persona) for i, (target, context) in enumerate(targets, 1)
            for persona in ([None] if cfg.steps["check"].enabled else []) + personas]
    results = parallel_map(lambda j: check(j[1], cfg, ctx, _label(p, j), step="perspective" if j[3] else "check",
                                           persona=j[3], context=j[2]), jobs, cfg.max_parallel)
    it.parts = list(results)
    per_target = [synthesize([r for j, r in zip(jobs, results) if j[0] == i], target, cfg, ctx,
                             f"{p}/synthesize/claim{i}") for i, (target, _) in enumerate(targets, 1)]
    it.parts += [r for r in per_target if r not in results]  # keep per-claim syntheses for the UI
    it.final = per_target[0] if len(per_target) == 1 else synthesize(per_target, it.input_text, cfg, ctx,
                                                                       f"{p}/synthesize/all")
    return it


def run_perspective(run: FactCheckRun, scientist: str, target: str, cfg: FactCheckConfig) -> CheckResult:
    """A disconnected call evaluating `target` strictly as `scientist` would (UI per-scientist buttons)."""
    ctx = RunContext(run, cfg)
    try:
        context = None if target.strip() == run.current_text.strip() else run.current_text
        result = check(target, cfg, ctx, f"perspective/{scientist}", step="perspective", persona=scientist,
                       context=context)
        run.perspectives.append(result)
        return result
    finally:
        ctx.close()


def synthesize_perspectives(run: FactCheckRun, cfg: FactCheckConfig) -> CheckResult:
    """Merge all perspective calls made so far (plus the latest iteration's result) into one report."""
    ctx = RunContext(run, cfg)
    try:
        latest = [run.iterations[-1].final] if run.iterations and run.iterations[-1].final else []
        result = synthesize(latest + run.perspectives, run.current_text, cfg, ctx, "perspectives/synthesize")
        run.perspectives.append(result)
        return result
    finally:
        ctx.close()


def parallel_map(fn, items: list, max_parallel: int) -> list:
    """Order-preserving parallel map; exceptions (e.g. budget exceeded, Stop) propagate to the caller."""
    if len(items) <= 1 or max_parallel <= 1:
        return [fn(x) for x in items]
    with ThreadPoolExecutor(max_workers=max_parallel) as pool:  # https://docs.python.org/3/library/concurrent.futures.html
        return list(pool.map(fn, items))


def _label(prefix: str, job) -> str:
    """Call label such as iter1/check/claim2 or iter1/perspective/claim2/Karl Popper."""
    i, _, _, persona = job
    return f"{prefix}/perspective/claim{i}/{persona}" if persona else f"{prefix}/check/claim{i}"


def _accuracy(result: CheckResult | None):
    """Overall accuracy of a result for log lines."""
    return result.summary.accuracy() if result and result.summary else None
