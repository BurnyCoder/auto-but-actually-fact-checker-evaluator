"""Phase: merge several results (per-scientist perspectives and/or per-claim checks) into one result.

Global context: used per claim (general check + scientist perspectives) and for the whole text (all per-claim
results -> one report with a corrected whole text); also behind the UI's "Synthesize perspectives" button. When the
synthesize step is disabled the results are concatenated deterministically (no corrected whole text then).
"""

from ..config import FactCheckConfig
from ..context import RunContext
from ..prompts import build_prompt
from ..results import CheckResult
from ..schema import FactCheckSummary
from .check import summarize_output


def source_name(r: CheckResult) -> str:
    """Readable provenance for a result inside the merge prompt."""
    who = r.persona or "general rigorous check"
    return f"{who} on claim: {r.target[:120]}" if r.step != "synthesize" else f"synthesis: {r.target[:120]}"


def merge_deterministic(results: list[CheckResult], target: str, label: str) -> CheckResult:
    """No-LLM merge: concatenated reports and pooled claims/issues."""
    report = "\n\n---\n\n".join(f"### {source_name(r)}\n\n{r.report}" for r in results)
    summaries = [r.summary for r in results if r.summary]
    summary = FactCheckSummary(claims=[c for s in summaries for c in s.claims],
                               issues=[i for s in summaries for i in s.issues]) if summaries else None
    return CheckResult(label=label, step="merge", target=target, report=report, summary=summary)


def synthesize(results: list[CheckResult], target: str, cfg: FactCheckConfig, ctx: RunContext,
               label: str) -> CheckResult:
    """One result for `target` from several; a single result is returned unchanged."""
    if len(results) == 1:
        return results[0]
    if not cfg.steps["synthesize"].enabled:
        return merge_deterministic(results, target, label)
    reports = [{"source": source_name(r), "text": r.report} for r in results]
    res = ctx.call("synthesize", build_prompt(cfg, "synthesize", target, reports=reports), label)
    return CheckResult(label=label, step="synthesize", target=target, report=res.text,
                       summary=summarize_output(res.text, cfg, ctx, label, failed=bool(res.error)))
