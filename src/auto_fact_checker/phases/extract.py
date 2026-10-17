"""Phase: extract self-contained claims from the whole text (used by the separate_call_per_claim strategy).

Global context: pipeline.run_iteration() fans the extracted claims out to one check call each; the default
template is a Claimify-style selection/disambiguation/decomposition prompt (prompts/extract/claimify.md).
"""

from ..config import FactCheckConfig
from ..context import RunContext
from ..prompts import build_prompt
from ..schema import ClaimList, ExtractedClaim, parse_block


def extract_claims(text: str, cfg: FactCheckConfig, ctx: RunContext, label: str) -> list[ExtractedClaim]:
    """Claims found by the extract step (at most cfg.max_claims); falls back to the whole text as one claim."""
    if not cfg.steps["extract"].enabled:
        return [ExtractedClaim(claim=text)]
    res = ctx.call("extract", build_prompt(cfg, "extract", text), label)
    parsed = parse_block(res.text, ClaimList)
    claims = [c for c in (parsed.claims if parsed else []) if c.claim.strip()][: cfg.max_claims]
    if not claims:
        ctx.log.warning("%s: no claims parsed, checking the whole text as one target", label)
    ctx.log.info("%s: %d claims: %s", label, len(claims), [c.claim for c in claims])
    return claims or [ExtractedClaim(claim=text)]
