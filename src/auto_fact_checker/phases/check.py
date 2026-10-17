"""Phase: fact-check one target (whole text or one claim), optionally from one scientist's perspective.

Global context: the core call of every strategy. step="check" uses the check StepConfig (and, with subagent
strategies, the Claude Code --agents definitions); step="perspective" uses the perspective StepConfig with a persona
(separate_call_per_scientist strategy and the UI's per-scientist buttons). The answer's JSON block is parsed (and
repaired if needed) into a FactCheckSummary.
"""

from ..config import FactCheckConfig
from ..context import RunContext
from ..prompts import build_agents, build_prompt
from ..results import CheckResult
from ..schema import FactCheckSummary, parse_block


def summarize_output(text: str, cfg: FactCheckConfig, ctx: RunContext, label: str) -> FactCheckSummary | None:
    """Parse the JSON summary; if it is missing/invalid and the repair step is enabled, ask the repair step."""
    summary = parse_block(text, FactCheckSummary)
    if summary is None and text.strip() and cfg.steps["repair"].enabled:
        ctx.log.warning("%s: JSON summary missing or invalid, running repair step", label)
        repaired = ctx.call("repair", build_prompt(cfg, "repair", "", report=text), f"{label}/repair")
        summary = parse_block(repaired.text, FactCheckSummary)
    if summary is None:
        ctx.log.error("%s: no parseable JSON summary", label)
    return summary


def check(target: str, cfg: FactCheckConfig, ctx: RunContext, label: str, *, step: str = "check",
          persona: str | None = None, context: str | None = None) -> CheckResult:
    """One check/perspective call on `target`; `context` is the full document when target is one claim."""
    prompt = build_prompt(cfg, step, target, context=context, persona=persona)
    agents = build_agents(cfg) if step == "check" and cfg.uses_subagents else None
    res = ctx.call(step, prompt, label, agents=agents)
    return CheckResult(label=label, step=step, target=target, persona=persona, report=res.text,
                       summary=summarize_output(res.text, cfg, ctx, label))
