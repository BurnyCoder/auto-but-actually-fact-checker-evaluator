"""Tests for config.py: granular per-step configuration, validation, presets and CLI overrides.

Global context: FactCheckConfig is the single source of truth for every run (UI, CLI, benchmark), so these tests
pin down its defaults, the (kind, provider) -> backend mapping and the preset round-trip the UI relies on.
"""

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
    with pytest.raises(ValidationError, match="subagent"):
        C.FactCheckConfig(claim_strategy="subagent_per_claim")  # default check step is an API call -> impossible
    steps = C.default_steps()
    steps["check"] = C.StepConfig(kind="agent", provider="anthropic", model="claude-haiku-5-5", allow_subagents=True)
    cfg = C.FactCheckConfig(steps=steps, claim_strategy="subagent_per_claim", scientist_strategy="subagent_per_scientist")
    assert cfg.uses_subagents  # derived flag used by the pipeline and the prompt builder


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
