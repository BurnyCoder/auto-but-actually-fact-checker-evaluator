"""Configuration: .env settings plus the granular fact-check configuration (every UI knob).

Local: pydantic models for per-step settings (StepConfig) and the whole run (FactCheckConfig), preset JSON I/O
and dotted-path CLI overrides.
Global context: FactCheckConfig is the single source of truth for a run. The Gradio UI (ui.py) renders its widgets
from these fields, presets in configs/presets/*.json are (partial) dumps of it, the CLI (__main__.py) and the
benchmark (bench/run.py) load it, and pipeline.py executes it. "Modes" such as single-call or per-claim agents are
only presets over these fields. Pydantic docs: https://docs.pydantic.dev/latest/concepts/models/ ;
pydantic-settings (.env loading): https://docs.pydantic.dev/latest/concepts/pydantic_settings/
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from jinja2 import TemplateError
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from . import catalog

ROOT = Path(__file__).resolve().parents[2]  # repo root: src/auto_fact_checker/config.py -> ../../
PROMPTS_DIR = ROOT / "prompts"  # all prompt text lives here (sections/, per-step template folders, options.json)
PRESETS_DIR = ROOT / "configs" / "presets"  # UI presets (the "modes")

STEPS = ("extract", "check", "perspective", "synthesize", "repair")  # pipeline steps, each with its own StepConfig
Kind = Literal["api", "agent"]  # api = one provider API request; agent = Codex / Claude Code CLI agent run
Provider = Literal["openai", "anthropic"]
Effort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]  # reasoning depth, mapped per backend;
# a model rejects levels it lacks (gpt-6-luna: none/low/medium/high/xhigh/max, no "minimal"; see its model page)
BACKENDS = {("api", "openai"): "openai_api", ("api", "anthropic"): "anthropic_api",
            ("agent", "openai"): "codex", ("agent", "anthropic"): "claude_code"}
DEFAULT_BLOCKED = []  # domains blocked from web search by default (benchmarks add dataset hosts)


class Settings(BaseSettings):
    """Process-wide settings read from the environment and the repo's .env file (never committed)."""

    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")
    openai_api_key: SecretStr | None = None  # SecretStr keeps keys out of logs/reprs
    anthropic_api_key: SecretStr | None = None
    anthropic_workspace_id: str | None = None  # required by keys not scoped to a workspace (API returns 400)
    agent_auth: Literal["subscription", "api_key"] = "subscription"  # how Claude Code / Codex authenticate
    spend_limit_usd: float = 10.0  # global cap on cumulative billed spend (logs/spend.jsonl)
    claude_bin: str | None = None  # optional explicit path to claude.exe
    codex_bin: str | None = None  # optional explicit path to codex.exe
    logs_dir: Path = Path("logs")
    runs_dir: Path = Path("runs")

    @field_validator("logs_dir", "runs_dir")
    @classmethod
    def _anchor(cls, p: Path) -> Path:
        """Relative directories are resolved against the repo root so runs from any cwd land in one place."""
        return p if p.is_absolute() else ROOT / p

    @property
    def ledger(self) -> Path:
        """Location of the persistent spend ledger."""
        return self.logs_dir / "spend.jsonl"


@lru_cache
def get_settings() -> Settings:
    """Cached Settings instance (tests construct Settings() directly to bypass the cache)."""
    return Settings()


@lru_cache
def options() -> dict:
    """List-valued prompt parts (verdict labels, scientists, ...) from prompts/options.json."""
    return json.loads((PROMPTS_DIR / "options.json").read_text(encoding="utf-8"))


def section_ids() -> list[str]:
    """All prompt section ids (file stems in prompts/sections/, sorted by their numeric prefix)."""
    return sorted(p.stem for p in (PROMPTS_DIR / "sections").glob("*.md"))


def default_sections() -> list[str]:
    """Sections enabled by default: all of them except those listed in options.json (e.g. the NeurIPS role)."""
    off = set(options().get("sections_off_by_default", []))
    return [s for s in section_ids() if s not in off]


class StepConfig(BaseModel):
    """Settings for one pipeline step: API call vs agent, provider, model, depth, search, subagents, prompt."""

    model_config = ConfigDict(extra="forbid")  # a typo such as "modle" must fail, not silently run defaults
    enabled: bool = True  # off: extract -> whole text, check/perspective -> no such calls (perspective buttons
    # still run), synthesize -> deterministic merge, repair -> no JSON repair
    kind: Kind = "api"
    provider: Provider = "openai"  # OpenAI is preferred for simple calls
    model: str = catalog.DEFAULT_MODEL["openai"]  # any catalog id (or a custom id typed in the UI)
    effort: Effort = "low"  # Anthropic/Claude Code map none/minimal -> low; OpenAI/Codex pass the value as is
    web_search: bool = False
    search_context_size: Literal["low", "medium", "high"] = "medium"  # OpenAI web_search context size
    max_searches: int = 5  # Anthropic max_uses / OpenAI max_tool_calls / instruction for agents
    blocked_domains: list[str] = Field(default_factory=lambda: list(DEFAULT_BLOCKED))
    allow_subagents: bool = False  # agents only: may the agent spawn subagents (Claude Code Agent tool / Codex
    # spawn_agent); always on for the check step under a subagent strategy
    max_subagents: int = 8  # upper bound stated to the orchestrating agent
    max_turns: int | None = None  # Claude Code --max-turns (None = unlimited)
    timeout_s: int = 900  # agents: wall-clock limit (process tree killed); API calls: SDK request timeout
    prompt_template: str = ""  # file name inside prompts/<step>/ ; "" = the step's default template
    prompt_override: str = ""  # full Jinja prompt replacing the template (use {{ text }} for the input)

    @model_validator(mode="after")
    def _model_matches_provider(self):
        """A catalogued model must belong to the chosen provider (custom, uncatalogued ids are allowed)."""
        info = catalog.MODELS.get(self.model)
        if info and info.provider != self.provider:
            raise ValueError(f"model {self.model} is a {info.provider} model but provider is {self.provider}")
        return self


DEFAULT_TEMPLATES = {"extract": "claimify.md", "check": "rigorous_sections.md", "perspective": "persona.md",
                     "synthesize": "merge.md", "repair": "repair_json.md"}


def default_steps() -> dict[str, StepConfig]:
    """Cheap, OpenAI-first defaults: web search only where evidence is gathered (check, perspective)."""
    searching = {"check", "perspective"}
    return {s: StepConfig(web_search=s in searching, prompt_template=DEFAULT_TEMPLATES[s]) for s in STEPS}


def backend_for(step: StepConfig) -> str:
    """Backend registry key for a step, e.g. ("agent", "anthropic") -> "claude_code"."""
    return BACKENDS[(step.kind, step.provider)]


def _opt(key: str):
    """Default factory returning a fresh copy of an options.json list (so instances never share lists)."""
    return lambda: list(options()[key])


def _runs_nothing(check_on: bool, scientist_strategy: str, scientists: list, perspective_on: bool) -> bool:
    """True when no call would run: check off and no separate perspective calls (validator and UI fixer)."""
    return not check_on and not (scientist_strategy == "separate_call_per_scientist" and scientists and perspective_on)


SEPARATE = {"subagent_per_claim": "separate_call_per_claim", "subagent_per_scientist": "separate_call_per_scientist"}


class FactCheckConfig(BaseModel):
    """Everything that defines a fact-checking run; rendered 1:1 as UI widgets."""

    model_config = ConfigDict(extra="forbid")
    steps: dict[str, StepConfig] = Field(default_factory=default_steps)
    claim_strategy: Literal["whole_text", "subagent_per_claim", "separate_call_per_claim"] = "whole_text"
    scientist_strategy: Literal["none", "subagent_per_scientist", "separate_call_per_scientist"] = "none"
    sections: list[str] = Field(default_factory=default_sections)  # which prompt parts go in
    degrees: list[str] = Field(default_factory=_opt("degrees"))
    verdict_labels: list[str] = Field(default_factory=_opt("verdict_labels"))
    styles: list[str] = Field(default_factory=_opt("styles"))
    claim_types: list[str] = Field(default_factory=_opt("claim_types"))
    scientists: list[str] = Field(default_factory=_opt("scientists"))  # named in the in-prompt scientists section
    perspective_scientists: list[str] = Field(default_factory=_opt("default_perspective_scientists"))
    conditions: list[str] = Field(default_factory=lambda: [c["name"] for c in options()["conditions"]])
    score_all_labels: bool = True  # score every selected verdict label per claim (False: only applicable ones)
    score_each_scientist: bool = False  # add a scored "<scientist>'s standards" condition per named scientist
    custom_instructions: str = ""  # appended after the selected sections
    max_claims: int = 15  # cap for claim extraction
    max_parallel: int = 4  # concurrent calls in per-claim / per-scientist strategies
    iterate_until_accurate: bool = False  # re-check corrections until model-rated scores or another stop condition apply
    accuracy_threshold: int = 90  # model-reported percentage every returned claim must reach
    max_iterations: int = 3
    stop_on_fixed_point: bool = True  # stop when the corrected text no longer changes
    max_cost_usd: float = 1.0  # per-run budget (the global SPEND_LIMIT_USD cap applies on top)

    @model_validator(mode="after")
    def _check_combinations(self):
        """Reject only impossible combinations (fix_combination resolves the same ones for the UI)."""
        if set(self.steps) != set(STEPS):
            raise ValueError(f"steps must be exactly {STEPS}")
        check = self.steps["check"]
        if self.uses_subagents and check.kind != "agent":
            raise ValueError("subagent strategies need an agent check step (kind='agent': Claude Code or Codex); "
                             "API calls cannot spawn subagents, use separate_call_per_claim / "
                             "separate_call_per_scientist instead")
        if _runs_nothing(check.enabled, self.scientist_strategy, self.perspective_scientists,
                         self.steps["perspective"].enabled):
            raise ValueError("with the check step disabled, enable the perspective step and use "
                             "separate_call_per_scientist with at least one perspective scientist "
                             "(otherwise nothing would run)")
        for name, sc in self.steps.items():  # a broken override would otherwise fail mid-run, after paid calls
            if sc.prompt_override.strip():
                from .prompts import build_prompt  # lazy: prompts.py imports this module
                try:  # render once with every variable set, as the pipeline would
                    build_prompt(self, name, "TEXT", context="CONTEXT", persona="Karl Popper", report="REPORT",
                                 reports=[{"source": "check", "text": "REPORT"}])
                except TemplateError as e:  # syntax errors and unknown variables (StrictUndefined)
                    raise ValueError(f"steps.{name}.prompt_override: {e}") from None
        return self

    @property
    def uses_subagents(self) -> bool:
        """True when the check agent must orchestrate claim-checker / scientist subagents."""
        return self.claim_strategy == "subagent_per_claim" or self.scientist_strategy == "subagent_per_scientist"

    def active_conditions(self) -> list[dict]:
        """Scored conditions in effect: selected in `conditions` AND their section is enabled (Lego toggles);
        plus one per named scientist when score_each_scientist and the scientists section are on."""
        on = set(self.sections)
        active = [c for c in options()["conditions"] if c["name"] in self.conditions and c["section"] in on]
        if self.score_each_scientist and "11_scientists" in on:
            active += [{"name": f"{s}'s standards", "section": "11_scientists",
                        "score": f"how well the claim holds up by {s}'s methods and standards of evidence"}
                       for s in self.scientists]
        return active


def fix_combination(data: dict, changed: tuple) -> list[str]:
    """Make a FactCheckConfig dump valid in place by adjusting a setting OTHER than `changed` (the path the user
    just edited); returns one note per adjustment.

    The UI runs this after every edit of a coupled widget, so it only offers working combinations; the CLI and
    presets still get the validators' errors. Rules (each mirrors one validator):
    - catalogued model of another provider: a model edit selects its provider, any other edit the provider's default
    - check step off with nothing to run: unticking it selects separate perspective calls, other edits re-enable it
    - subagent strategy with an API check step: a kind edit maps strategies to SEPARATE, other edits select an agent
    """
    notes, steps = [], data["steps"]
    for name, sc in steps.items():
        info = catalog.MODELS.get(sc["model"])
        if info and info.provider != sc["provider"]:
            if changed == ("steps", name, "model"):
                sc["provider"] = info.provider
                notes.append(f"{name} step: provider set to {info.provider} for {sc['model']}")
            else:
                sc["model"] = catalog.DEFAULT_MODEL[sc["provider"]]
                notes.append(f"{name} step: model set to {sc['model']}, the {sc['provider']} default")
    check, persp = steps["check"], steps["perspective"]
    if _runs_nothing(check["enabled"], data["scientist_strategy"], data["perspective_scientists"], persp["enabled"]):
        if changed == ("steps", "check", "enabled"):
            data["scientist_strategy"], persp["enabled"] = "separate_call_per_scientist", True
            data["perspective_scientists"] = data["perspective_scientists"] or _opt("default_perspective_scientists")()
            notes.append("Check step off: the run now makes one separate perspective call per scientist")
        else:
            check["enabled"] = True
            notes.append("Check step switched back on (otherwise nothing would run)")
    if {data["claim_strategy"], data["scientist_strategy"]} & set(SEPARATE) and check["kind"] != "agent":
        if changed == ("steps", "check", "kind"):
            data["claim_strategy"] = SEPARATE.get(data["claim_strategy"], data["claim_strategy"])
            data["scientist_strategy"] = SEPARATE.get(data["scientist_strategy"], data["scientist_strategy"])
            notes.append("API calls cannot spawn subagents: strategies switched to one separate call each")
        else:
            check["kind"] = "agent"
            notes.append(f"Subagents need an agent: the check step is now a "
                         f"{'Codex' if check['provider'] == 'openai' else 'Claude Code'} agent")
    return notes


def deep_merge(base: dict, patch: dict) -> dict:
    """Recursively merge patch into a copy of base (dicts merge, everything else is replaced)."""
    out = dict(base)
    for k, v in patch.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_preset(path: Path | str) -> FactCheckConfig:
    """Load a full or partial preset JSON; partial presets are deep-merged over the defaults."""
    p = Path(path)
    if not p.exists() and not p.suffix:  # allow bare preset names like "L1_single_call_search"
        p = PRESETS_DIR / f"{p}.json"
    patch = json.loads(p.read_text(encoding="utf-8"))
    patch.pop("_comment", None)  # presets may carry a human-readable description
    return FactCheckConfig.model_validate(deep_merge(FactCheckConfig().model_dump(), patch))


def save_preset(cfg: FactCheckConfig, path: Path | str) -> Path:
    """Write the full configuration as pretty JSON (loadable by load_preset and the UI)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
    return p


def list_presets() -> list[str]:
    """Preset names available in configs/presets/ (shown in the UI's preset dropdown)."""
    return sorted(p.stem for p in PRESETS_DIR.glob("*.json"))


def apply_overrides(cfg: FactCheckConfig, overrides: list[str]) -> FactCheckConfig:
    """Apply CLI overrides like 'steps.check.model=gpt-6.1-sol'; values are parsed as JSON when possible."""
    data = cfg.model_dump()
    for item in overrides:
        key, _, raw = item.partition("=")
        try:
            value = json.loads(raw)  # numbers, booleans, lists, quoted strings
        except json.JSONDecodeError:
            value = raw  # bare strings such as model ids
        *parents, leaf = key.strip().split(".")
        node = data
        for part in parents:
            node = node[part]
        node[leaf] = value
    return FactCheckConfig.model_validate(data)
