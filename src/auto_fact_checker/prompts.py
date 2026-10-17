"""Prompt assembly: toggleable sections + list options + per-step templates (+ optional free-text override).

Local: renders prompts/ files with Jinja2. Sections (prompts/sections/NN_*.md) are the user's original prompt split
into toggles; list-valued parts (verdict labels, scientists, ...) come from the config; every step has a folder of
templates (prompts/<step>/*.md) and the selected template wraps the rendered sections, the input text and the JSON
output contract (prompts/json_summary.md).
Global context: phases/*.py call build_prompt() for every LLM call and the Claude Code backend writes
build_agents() to an --agents file, so the UI's prompt toggles, template dropdowns and override boxes all act here.
Jinja2 docs: https://jinja.palletsprojects.com/en/stable/api/ (Environment, FileSystemLoader, StrictUndefined,
trim_blocks/lstrip_blocks whitespace control) and https://jinja.palletsprojects.com/en/stable/templates/#include
"""

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .config import DEFAULT_TEMPLATES, PROMPTS_DIR, FactCheckConfig, section_ids

# StrictUndefined: a template using an unknown variable raises instead of silently rendering "" (tests rely on it).
ENV = Environment(loader=FileSystemLoader(PROMPTS_DIR), undefined=StrictUndefined, trim_blocks=True,
                  lstrip_blocks=True, keep_trailing_newline=False, autoescape=False)


def template_choices(step: str) -> list[str]:
    """Template file names available for a step (any *.md dropped into prompts/<step>/ appears in the UI)."""
    return sorted(p.name for p in (PROMPTS_DIR / step).glob("*.md"))


def _vars(cfg: FactCheckConfig, step: str, persona: str | None) -> dict:
    """Variables shared by every template: lists, flags and strategy settings (all always defined)."""
    sc = cfg.steps[step]
    return {"web_search": sc.web_search, "persona": persona, "degrees": cfg.degrees,
            "verdict_labels": cfg.verdict_labels, "styles": cfg.styles, "claim_types": cfg.claim_types,
            "scientists": cfg.scientists, "perspective_scientists": cfg.perspective_scientists,
            "custom_instructions": cfg.custom_instructions.strip(), "max_claims": cfg.max_claims,
            "max_subagents": sc.max_subagents, "per_claim": cfg.claim_strategy == "subagent_per_claim",
            "per_scientist": cfg.scientist_strategy == "subagent_per_scientist",
            "uncertainty": "23_uncertainty" in cfg.sections, "classify": "21_claim_classification" in cfg.sections}


def sections_text(cfg: FactCheckConfig, step: str, persona: str | None = None) -> str:
    """Selected sections rendered in their numeric order; sections that render empty (e.g. search-only) vanish."""
    v = _vars(cfg, step, persona)
    chosen = [s for s in section_ids() if s in set(cfg.sections)]  # file order, not click order
    rendered = (ENV.get_template(f"sections/{s}.md").render(**v).strip() for s in chosen)
    return "\n".join(r for r in rendered if r)


def output_contract(cfg: FactCheckConfig, step: str = "check") -> str:
    """The JSON summary instructions; fields for uncertainty / claim types appear only when those sections are on."""
    return ENV.get_template("json_summary.md").render(**_vars(cfg, step, None)).strip()


def build_prompt(cfg: FactCheckConfig, step: str, text: str, *, context: str | None = None,
                 persona: str | None = None, reports: list[dict] | None = None, report: str | None = None) -> str:
    """Final prompt for one call of `step` on `text` (a whole document or one extracted claim).

    context: full document when `text` is one extracted claim; persona: scientist for perspective calls;
    reports: [{source, text}] for synthesis; report: raw report text for JSON repair.
    """
    sc = cfg.steps[step]
    v = _vars(cfg, step, persona) | {
        "text": text, "context": context, "reports": reports or [], "report": report or "",
        "sections_text": sections_text(cfg, step, persona), "output_contract": output_contract(cfg, step)}
    if sc.prompt_override.strip():  # user-written full prompt replaces the template entirely
        return ENV.from_string(sc.prompt_override).render(**v).strip()
    prompt = ENV.get_template(f"{step}/{sc.prompt_template or DEFAULT_TEMPLATES[step]}").render(**v).strip()
    if step == "check" and cfg.uses_subagents:  # the check agent orchestrates subagents around the same task
        prompt = ENV.get_template("subagents/orchestrator.md").render(**v, inner_prompt=prompt).strip()
    return prompt


def build_agents(cfg: FactCheckConfig) -> dict[str, dict]:
    """Claude Code --agents JSON: subagent definitions for the chosen subagent strategies.

    Format (description, prompt, tools/disallowedTools, model): https://code.claude.com/docs/en/sub-agents
    Omitting "tools" makes subagents inherit the main agent's tools (incl. WebSearch/WebFetch).
    """
    v = _vars(cfg, "check", None)
    deny = [] if cfg.steps["check"].web_search else ["WebSearch", "WebFetch"]  # mirror the check step's search toggle
    agents = {}
    if v["per_claim"]:
        agents["claim-checker"] = {
            "description": "Use once per extracted claim: deep web research and a full rigorous fact-check of ONE claim.",
            "prompt": ENV.get_template("subagents/claim_checker.md").render(
                **v, sections_text=sections_text(cfg, "check")).strip(),
            "model": "inherit", "disallowedTools": deny}
    if v["per_scientist"]:
        persona = "the scientist named in your task"  # the lead agent names the scientist per launch
        agents["scientist-perspective"] = {
            "description": "Use once per scientist (and claim): evaluate the material strictly from ONE named scientist's perspective.",
            "prompt": ENV.get_template("subagents/scientist.md").render(
                **v, sections_text=sections_text(cfg, "check", persona)).strip(),
            "model": "inherit", "disallowedTools": deny}
    return agents
