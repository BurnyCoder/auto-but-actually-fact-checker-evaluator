"""Machine-readable output contract of the prompts and a tolerant parser for it.

Local: pydantic models mirroring prompts/json_summary.md (claims with 0-100 accuracy and confidence, typed claim
classes, scored labels with degrees, scored condition assessments, corrected claim/text, issues) and prompts/extract/*.md (claim lists), plus parse_block() which finds the
last ```json block in a model's answer and repairs common JSON mistakes.
Global context: phases parse every check/perspective/synthesis answer into FactCheckSummary; its scores drive the
iterate-until-accurate loop, the UI's claims table and the benchmark's predictions. json_repair docs:
https://github.com/mangiucugna/json_repair ; pydantic BeforeValidator:
https://docs.pydantic.dev/latest/concepts/validators/#field-before-validator
"""

import re
from typing import Annotated, TypeVar

import json_repair
from pydantic import BaseModel, BeforeValidator, ConfigDict, ValidationError


def _pct(v):
    """Accept 85, "85", "85%", 0.85-style strings; clamp to 0-100; anything unparseable becomes None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, str):
        m = re.search(r"-?\d+(\.\d+)?", v)
        if not m:
            return None
        v = float(m.group())
    try:
        return min(max(float(v), 0.0), 100.0)
    except (TypeError, ValueError):
        return None


Pct = Annotated[float | None, BeforeValidator(_pct)]


def _labels(v):
    """Labels may come as plain strings ("misleading") instead of objects."""
    return [{"label": x} if isinstance(x, str) else x for x in (v or [])]


def _strs(v):
    """A single string where a list was expected becomes a one-item list."""
    return [v] if isinstance(v, str) else (v or [])


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")  # models may add fields; ignore them


def _types(v):
    """Claim types may come as strings ("fact") or objects ({"type": "fact", "confidence_pct": 80})."""
    return [{"type": x} if isinstance(x, str) else x for x in _strs(v)]


class LabelScore(_Lenient):
    """One verdict label (e.g. 'oversimplified') with its degree, how much it applies and the confidence."""

    label: str = ""
    degree: str | None = None  # fully | partially | slightly
    score_pct: Pct = None
    confidence_pct: Pct = None


class Assessment(_Lenient):
    """One evaluative condition (e.g. 'Bayesian perspective') with a finding, a defined 0-100 score and confidence."""

    condition: str = ""
    finding: str = ""
    score_pct: Pct = None
    confidence_pct: Pct = None


class ClaimType(_Lenient):
    """One claim classification (e.g. 'falsifiable') with the confidence that it applies."""

    type: str = ""
    confidence_pct: Pct = None


class ClaimVerdict(_Lenient):
    claim: str = ""
    claim_types: Annotated[list[ClaimType], BeforeValidator(_types)] = []
    accuracy_pct: Pct = None
    confidence_pct: Pct = None
    labels: Annotated[list[LabelScore], BeforeValidator(_labels)] = []
    assessments: list[Assessment] = []
    corrected_claim: str | None = None


class FactCheckSummary(_Lenient):
    claims: list[ClaimVerdict] = []
    overall_accuracy_pct: Pct = None
    overall_confidence_pct: Pct = None
    corrected_text: str | None = None
    issues: Annotated[list[str], BeforeValidator(_strs)] = []

    def accuracy(self) -> float | None:
        """Overall accuracy, falling back to the mean of the per-claim accuracies."""
        if self.overall_accuracy_pct is not None:
            return self.overall_accuracy_pct
        scores = [c.accuracy_pct for c in self.claims if c.accuracy_pct is not None]
        return sum(scores) / len(scores) if scores else None

    def all_accurate(self, threshold: float) -> bool:
        """True when there is at least one claim and every claim reaches the threshold (missing scores fail)."""
        return bool(self.claims) and all((c.accuracy_pct or 0) >= threshold for c in self.claims)


class ExtractedClaim(_Lenient):
    claim: str
    quote: str = ""
    note: str = ""


class ClaimList(_Lenient):
    claims: Annotated[list[ExtractedClaim], BeforeValidator(lambda v: [{"claim": x} if isinstance(x, str) else x
                                                                         for x in (v or [])])] = []


T = TypeVar("T", bound=BaseModel)
FENCE = re.compile(r"```\s*json\s*\n(.*?)```", re.IGNORECASE | re.DOTALL)  # ```json ... ``` (any case)


def parse_block(text: str, model: type[T]) -> T | None:
    """Parse the LAST fenced json block (falling back to the last {...} span) into `model`; None if impossible."""
    candidates = FENCE.findall(text or "")[::-1]
    if not candidates and "{" in (text or ""):
        candidates = [text[text.index("{"): text.rindex("}") + 1]]  # unfenced JSON answer
    for raw in candidates:
        data = json_repair.loads(raw)  # fixes trailing commas, single quotes, unquoted keys, truncation
        if isinstance(data, dict):
            try:
                return model.model_validate(data)
            except ValidationError:
                continue
    return None
