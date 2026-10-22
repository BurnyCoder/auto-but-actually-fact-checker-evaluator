"""Rendering of runs for humans: Markdown reports and table rows (claims, labels, conditions, calls).

Global context: shared by the Gradio UI (Markdown + Dataframe components) and the CLI (`afc check` writes
runs/<id>/report.md), so both show exactly the same information.
"""

from .results import CheckResult, FactCheckRun
from .schema import FactCheckSummary


def _pct(v) -> str:
    return "" if v is None else f"{v:.0f}%"


def claims_rows(summary: FactCheckSummary | None) -> list[dict]:
    """One row per returned claim: model-reported scores and classifications, not calibrated probabilities."""
    rows = []
    for i, c in enumerate(summary.claims if summary else [], 1):
        top = sorted((lab for lab in c.labels if (lab.score_pct or 0) > 0), key=lambda lab: -(lab.score_pct or 0))
        rows.append({"#": i, "claim": c.claim, "accuracy": _pct(c.accuracy_pct), "confidence": _pct(c.confidence_pct),
                     "types": ", ".join(f"{t.type} ({_pct(t.confidence_pct)})" if t.confidence_pct is not None
                                        else t.type for t in c.claim_types),
                     "top labels": ", ".join(f"{lab.degree + ' ' if lab.degree else ''}{lab.label} "
                                             f"{_pct(lab.score_pct)}" for lab in top[:6]),
                     "corrected claim": c.corrected_claim or ""})
    return rows


def labels_rows(summary: FactCheckSummary | None) -> list[dict]:
    """Every scored label of every claim (the full verdict matrix with confidences)."""
    return [{"#": i, "label": lab.label, "degree": lab.degree or "", "score": _pct(lab.score_pct),
             "confidence": _pct(lab.confidence_pct)}
            for i, c in enumerate(summary.claims if summary else [], 1) for lab in c.labels]


def conditions_rows(summary: FactCheckSummary | None) -> list[dict]:
    """Every scored condition (perspectives, strengths/weaknesses, predictive power, ...) of every claim."""
    return [{"#": i, "condition": a.condition, "score": _pct(a.score_pct), "confidence": _pct(a.confidence_pct),
             "finding": a.finding}
            for i, c in enumerate(summary.claims if summary else [], 1) for a in c.assessments]


def calls_rows(run: FactCheckRun) -> list[dict]:
    """One row per LLM call with backend, model, tokens, searches, cost and errors."""
    return [{"label": c.label, "backend": c.backend, "model": c.model, "in": c.input_tokens, "out": c.output_tokens,
             "searches": c.web_searches, "estimated cost $": "unknown" if c.cost_usd is None else f"{c.cost_usd:.4f}",
             "billed": c.billed, "s": c.duration_s, "error": c.error or ""} for c in run.calls]


def iterations_rows(run: FactCheckRun) -> list[dict]:
    """One row per iteration: overall accuracy/confidence, number of claims, issues."""
    rows = []
    for it in run.iterations:
        s = it.final.summary if it.final else None
        rows.append({"iteration": it.index, "accuracy": _pct(s.accuracy() if s else None),
                     "confidence": _pct(s.overall_confidence_pct if s else None),
                     "claims": len(s.claims) if s else 0, "issues": len(s.issues) if s else 0,
                     "input": it.input_text[:200]})
    return rows


def result_markdown(r: CheckResult) -> str:
    """A single result's report (the model's own Markdown, JSON block included)."""
    who = f" — {r.persona}" if r.persona else ""
    return f"### {r.label}{who}\n\n{r.report}"


def run_markdown(run: FactCheckRun) -> str:
    """Whole-run report: status line, then each iteration's final report, then perspective calls."""
    parts = [f"**Run** `{run.run_id}` — status **{run.status}**"
             + (f" ({run.stop_reason})" if run.stop_reason else "")
             + f" — {len(run.calls)} calls, known estimates ${run.total_cost_usd:.4f} "
               f"(API-key ${run.billed_cost_usd:.4f}; {run.unknown_cost_calls} calls with unknown cost)"]
    for it in run.iterations:
        parts.append(f"## Iteration {it.index}")
        if it.final:
            parts.append(result_markdown(it.final))
    if run.perspectives:
        parts.append("## Perspective calls")
        parts += [result_markdown(p) for p in run.perspectives]
    return "\n\n".join(parts)
