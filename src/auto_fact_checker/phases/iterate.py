"""Phase: decide whether another fact-checking iteration over the corrected text is needed.

Global context: pipeline.run_fact_check() calls should_stop() after every iteration and records the reason; it ends
the loop only when iterate_until_accurate allows more than one pass. "One more iteration" ignores it and always
runs exactly one more pass.
"""

import re

from ..config import FactCheckConfig
from ..results import FactCheckRun


def _norm(text: str) -> str:
    """Whitespace/case-insensitive comparison key for the fixed-point test."""
    return re.sub(r"\s+", " ", text).strip().lower()


def should_stop(run: FactCheckRun, cfg: FactCheckConfig) -> str | None:
    """Reason to stop iterating, or None to continue."""
    last = run.iterations[-1]
    summary = last.final.summary if last.final else None
    if summary is None:
        return "no parseable JSON summary"
    if summary.all_accurate(cfg.accuracy_threshold):
        return f"model rates all returned claims >= {cfg.accuracy_threshold}% accurate"
    if not (summary.corrected_text or "").strip():
        return "no corrected text to re-check"
    if cfg.stop_on_fixed_point and _norm(summary.corrected_text) == _norm(last.input_text):
        return "fixed point: corrected text unchanged"
    return None
