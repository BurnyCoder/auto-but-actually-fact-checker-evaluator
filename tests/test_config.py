"""Tests for config.py: granular per-step configuration, validation, presets and CLI overrides.

Global context: FactCheckConfig is the single source of truth for every run (UI, CLI, benchmark), so these tests
pin down its defaults, the (kind, provider) -> backend mapping and the preset round-trip the UI relies on.
"""

import itertools

import pytest
from pydantic import ValidationError

from auto_fact_checker import config as C


def test_defaults_are_valid_and_cheap():
    cfg = C.FactCheckConfig()  # all defaults must validate without any preset
    assert set(cfg.steps) == set(C.STEPS)  # one StepConfig per pipeline step
    assert cfg.steps["check"].web_search is True  # the rigorous prompt asks to search the web
    assert cfg.steps["extract"].web_search is False  # extraction is pure text processing
    assert all(s.model in ("gpt-6-luna", "claude-haiku-5-5") for s in cfg.steps.values())  # cheap defaults
    assert "Karl Popper" in cfg.scientists and "fully" in cfg.degrees  # lists loaded from prompts/options.json


def test_backend_mapping():
    assert C.backend_for(C.StepConfig(kind="api", provider="openai")) == "openai_api"
    assert C.backend_for(C.StepConfig(kind="api", provider="anthropic", model="claude-haiku-5-5")) == "anthropic_api"
    assert C.backend_for(C.StepConfig(kind="agent", provider="openai")) == "codex"
    assert C.backend_for(C.StepConfig(kind="agent", provider="anthropic", model="claude-haiku-5-5")) == "claude_code"


def test_subagent_strategy_requires_agent_check_step():
    with pytest.raises(ValidationError, match="separate_call_per_claim"):
        C.FactCheckConfig(claim_strategy="subagent_per_claim")  # default check step is an API call -> impossible
    for provider, model in C.catalog.DEFAULT_MODEL.items():  # Claude Code and Codex; allow_subagents is implied
        steps = C.default_steps()
        steps["check"] = C.StepConfig(kind="agent", provider=provider, model=model)
        cfg = C.FactCheckConfig(steps=steps, claim_strategy="subagent_per_claim",
                                scientist_strategy="subagent_per_scientist")
        assert cfg.uses_subagents  # derived flag used by the pipeline and the prompt builder


EDITED = [("claim_strategy",), ("scientist_strategy",), ("perspective_scientists",), ("steps", "check", "kind"),
          ("steps", "check", "provider"), ("steps", "check", "model"), ("steps", "check", "enabled"),
          ("steps", "perspective", "enabled")]


def _get(data: dict, path: tuple):
    for key in path:
        data = data[key]
    return data


@pytest.mark.parametrize("edited", EDITED)
def test_fix_combination_makes_every_combination_valid_and_keeps_the_edit(edited):
    """The UI calls fix_combination after each edit, so no widget state can produce an 'Invalid configuration'."""
    for cs, ss, kind, provider, model, check_on, persp_on, scientists in itertools.product(
            ["whole_text", "subagent_per_claim", "separate_call_per_claim"],
            ["none", "subagent_per_scientist", "separate_call_per_scientist"], ["api", "agent"],
            ["openai", "anthropic"], ["gpt-6-luna", "claude-haiku-5-5"], [True, False], [True, False],
            [[], ["Karl Popper"]]):
        data = C.FactCheckConfig().model_dump()
        data.update(claim_strategy=cs, scientist_strategy=ss, perspective_scientists=scientists)
        data["steps"]["check"].update(kind=kind, provider=provider, model=model, enabled=check_on)
        data["steps"]["perspective"]["enabled"] = persp_on
        before = _get(data, edited)
        C.fix_combination(data, edited)
        C.FactCheckConfig.model_validate(data)  # never raises
        assert _get(data, edited) == before  # the fix changes another setting, never the one just edited


def test_fix_combination_directions():
    data = C.FactCheckConfig().model_dump() | {"claim_strategy": "subagent_per_claim"}
    assert C.fix_combination(data, ("claim_strategy",)) and data["steps"]["check"]["kind"] == "agent"
    data["steps"]["check"]["kind"] = "api"  # switching back to an API call drops the subagents instead
    C.fix_combination(data, ("steps", "check", "kind"))
    assert data["claim_strategy"] == "separate_call_per_claim" and data["steps"]["check"]["kind"] == "api"
    data = C.FactCheckConfig().model_dump()
    data["steps"]["check"]["model"] = "claude-haiku-5-5"  # picking a Claude model selects its provider
    C.fix_combination(data, ("steps", "check", "model"))
    assert data["steps"]["check"]["provider"] == "anthropic"
    data["steps"]["check"]["provider"] = "openai"  # picking a provider selects its default model
    C.fix_combination(data, ("steps", "check", "provider"))
    assert data["steps"]["check"]["model"] == C.catalog.DEFAULT_MODEL["openai"]
    data["steps"]["check"]["enabled"] = False  # check off -> perspective-only run
    C.fix_combination(data, ("steps", "check", "enabled"))
    assert data["scientist_strategy"] == "separate_call_per_scientist" and data["steps"]["perspective"]["enabled"]
    data["scientist_strategy"] = "none"  # leaving perspective-only mode turns the check back on
    C.fix_combination(data, ("scientist_strategy",))
    assert data["steps"]["check"]["enabled"]
    assert C.fix_combination(C.FactCheckConfig().model_dump(), ("claim_strategy",)) == []  # valid: no change


def test_preset_round_trip_and_partial_merge(tmp_path):
    cfg = C.FactCheckConfig(max_iterations=7, custom_instructions="Be terse.")
    path = tmp_path / "p.json"
    C.save_preset(cfg, path)  # full dump
    assert C.load_preset(path) == cfg  # identical after reload
    partial = tmp_path / "partial.json"
    partial.write_text('{"steps": {"check": {"model": "gpt-6.1-sol"}}, "max_claims": 3}', encoding="utf-8")
    merged = C.load_preset(partial)  # partial presets are deep-merged over the defaults
    assert merged.steps["check"].model == "gpt-6.1-sol" and merged.steps["check"].web_search is True
    assert merged.max_claims == 3 and merged.steps["extract"] == C.default_steps()["extract"]


def test_apply_overrides_dotted_paths():
    cfg = C.apply_overrides(C.FactCheckConfig(), ["steps.check.model=gpt-6.1-sol", "max_iterations=5",
                                                  'sections=["01_task"]', "steps.check.web_search=false"])
    assert cfg.steps["check"].model == "gpt-6.1-sol" and cfg.max_iterations == 5
    assert cfg.sections == ["01_task"] and cfg.steps["check"].web_search is False


def test_settings_resolve_relative_dirs(monkeypatch):
    monkeypatch.setenv("LOGS_DIR", "some_logs")
    s = C.Settings()
    assert s.logs_dir == C.ROOT / "some_logs"  # relative paths are anchored at the repo root


def test_typos_and_impossible_combinations_are_rejected():
    with pytest.raises(ValidationError):
        C.apply_overrides(C.FactCheckConfig(), ["steps.check.modle=gpt-6.1-sol"])  # typo -> error, not defaults
    with pytest.raises(ValidationError, match="nothing would run"):
        steps = C.default_steps()
        steps["check"] = C.StepConfig(enabled=False)
        C.FactCheckConfig(steps=steps, scientist_strategy="separate_call_per_scientist", perspective_scientists=[])
    with pytest.raises(ValidationError, match="nothing would run"):  # check and perspective both off
        steps["perspective"] = C.StepConfig(enabled=False)
        C.FactCheckConfig(steps=steps, scientist_strategy="separate_call_per_scientist")
    with pytest.raises(ValidationError, match="anthropic model"):
        C.StepConfig(provider="openai", model="claude-haiku-5-5")
    C.StepConfig(provider="openai", model="my-custom-model")  # uncatalogued ids stay allowed
