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


def _strs(v):
    """A single value where a list was expected becomes a one-item list; null becomes []."""
    return [] if v is None else v if isinstance(v, list) else [v]


def _text(v):
    """Null -> "", a list -> its items joined (e.g. "degree": ["fully"]), anything else -> str."""
    return "" if v is None else ", ".join(map(str, v)) if isinstance(v, list) else str(v)


def _objs(key: str):
    """Before-validator for lists of objects that models sometimes give as bare strings (or nulls)."""
    return BeforeValidator(lambda v: [{key: x} if isinstance(x, str) else x for x in _strs(v) if x is not None])


Text = Annotated[str, BeforeValidator(_text)]
OptText = Annotated[str | None, BeforeValidator(lambda v: None if v is None else _text(v))]


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")  # models may add fields; ignore them


class LabelScore(_Lenient):
    """One verdict label (e.g. 'oversimplified') with its degree, how much it applies and the confidence."""

    label: Text = ""
    degree: OptText = None  # fully | partially | slightly
    score_pct: Pct = None
    confidence_pct: Pct = None


class Assessment(_Lenient):
    """One evaluative condition (e.g. 'Bayesian perspective') with a finding, a defined 0-100 score and confidence."""

    condition: Text = ""
    finding: Text = ""
    score_pct: Pct = None
    confidence_pct: Pct = None


class ClaimType(_Lenient):
    """One claim classification (e.g. 'falsifiable') with the confidence that it applies."""

    type: Text = ""
    confidence_pct: Pct = None


class ClaimVerdict(_Lenient):
    claim: Text = ""
    claim_types: Annotated[list[ClaimType], _objs("type")] = []
    accuracy_pct: Pct = None
    confidence_pct: Pct = None
    labels: Annotated[list[LabelScore], _objs("label")] = []
    assessments: Annotated[list[Assessment], _objs("condition")] = []
    corrected_claim: OptText = None


class FactCheckSummary(_Lenient):
    claims: Annotated[list[ClaimVerdict], _objs("claim")] = []
    overall_accuracy_pct: Pct = None
    overall_confidence_pct: Pct = None
    corrected_text: OptText = None
    issues: Annotated[list[Text], BeforeValidator(_strs)] = []

    def meaningful(self) -> bool:
        """A usable summary has claims or an overall score (an empty or unrelated JSON object does not)."""
        return bool(self.claims) or self.overall_accuracy_pct is not None

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
    claim: Text = ""
    quote: str = ""
    note: str = ""


class ClaimList(_Lenient):
    claims: Annotated[list[ExtractedClaim], _objs("claim")] = []


class JudgeVerdict(_Lenient):
    """Gold-evidence judge output (Exp07): is a text correct according to the cited abstract(s)?"""

    main_claim_entailed: bool | None = None  # the central assertion is supported by the gold evidence
    contradicts_evidence: bool | None = None  # some statement conflicts with the gold evidence
    same_question: bool | None = None  # still a specific claim about the original question (not vague/off-topic)
    verdict: Text = ""
    explanation: Text = ""

    def correct(self) -> bool | None:
        """correct = entailed and not contradicted and on the same question; None when any field is missing."""
        fields = (self.main_claim_entailed, self.contradicts_evidence, self.same_question)
        return None if None in fields else (self.main_claim_entailed and not self.contradicts_evidence
                                            and self.same_question)


class InjectedError(_Lenient):
    """One error deliberately inserted into a benchmark passage (Exp08)."""

    error_type: Text = ""
    original_sentence: Text = ""
    perturbed_sentence: Text = ""
    false_fact: Text = ""
    true_fact: Text = ""


class InjectionList(_Lenient):
    errors: Annotated[list[InjectedError], BeforeValidator(_strs)] = []


class RefError(_Lenient):
    id: int | None = None
    status: Text = ""  # corrected | partially | uncorrected


FIX_POINTS = {"corrected": 1.0, "partially": 0.5, "partial": 0.5, "uncorrected": 0.0}


class RefVerdict(_Lenient):
    """Reference judge output (Exp08): status per injected error, introduced errors, holistic 0-100 accuracy."""

    errors: Annotated[list[RefError], BeforeValidator(_strs)] = []
    introduced_errors: Annotated[list[Text], BeforeValidator(_strs)] = []
    overall_accuracy_pct: Pct = None

    def fix_scores(self, ids: list[int]) -> dict[int, float | None]:
        """1 / 0.5 / 0 per expected error id (None when the judge skipped it or used an unknown status)."""
        given = {e.id: FIX_POINTS.get(e.status.strip().lower()) for e in self.errors if e.id is not None}
        return {i: given.get(i) for i in ids}


T = TypeVar("T", bound=BaseModel)
FENCE = re.compile(r"```\s*json\s*\n(.*?)```", re.IGNORECASE | re.DOTALL)  # ```json ... ``` (any case)


def parse_block(text: str, model: type[T], accept=None) -> T | None:
    """Parse the LAST usable fenced json block (falling back to the {...} span) into `model`; None if impossible.

    accept(obj) -> bool can reject parsed-but-useless objects so earlier blocks (or the repair step) are tried.
    """
    text = text or ""
    candidates = FENCE.findall(text)[::-1]
    if not candidates and "{" in text:
        end = text.rfind("}")
        candidates = [text[text.index("{"): end + 1 if end > text.index("{") else len(text)]]  # unfenced/truncated
    for raw in candidates:
        data = json_repair.loads(raw)  # fixes trailing commas, single quotes, unquoted keys, truncation
        if isinstance(data, dict):
            try:
                obj = model.model_validate(data)
            except ValidationError:
                continue
            if accept is None or accept(obj):
                return obj
    return None
