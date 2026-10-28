"""Tests for ui.py: the app builds, every config field round-trips through its widgets, previews and streaming work.

Global context: the UI must expose every FactCheckConfig knob (per step and global) and reproduce presets exactly,
otherwise "modes are presets over granular settings" would silently drop settings.
"""

import random

import gradio as gr
import pytest

from auto_fact_checker import config as C
from auto_fact_checker import ui
from auto_fact_checker.pipeline import run_fact_check
from auto_fact_checker.results import new_run


@pytest.fixture(scope="module")
def demo():
    return ui.build_ui()


def test_every_field_has_a_widget(demo):
    paths = {k.path for k in demo.afc_knobs}
    top = {f for f in C.FactCheckConfig.model_fields if f != "steps"}
    assert {(f,) for f in top} <= paths
    assert {("steps", s, f) for s in C.STEPS for f in C.StepConfig.model_fields} <= paths


@pytest.mark.parametrize("preset", C.list_presets())
def test_presets_round_trip_through_widgets(demo, preset):
    cfg = C.load_preset(preset)
    cfg.scientists = cfg.scientists + ["My Custom Scientist"]  # extras go through the companion textbox
    assert ui.cfg_from(demo.afc_knobs, ui.values_from(demo.afc_knobs, cfg)) == cfg


def test_coupled_edit_adjusts_the_other_widgets(demo):
    """Choosing a subagent strategy with the default API check step switches the check step to an agent."""
    knobs = demo.afc_knobs
    vals = ui.values_from(knobs, C.FactCheckConfig())
    vals[next(i for i, k in enumerate(knobs) if k.path == ("claim_strategy",))] = "subagent_per_claim"
    with pytest.raises(Exception, match="Invalid configuration"):
        ui.cfg_from(knobs, vals)  # the pop-up users saw before the fix
    new, notes = ui.fix_values(knobs, ("claim_strategy",), vals)
    cfg = ui.cfg_from(knobs, new)
    assert notes and cfg.claim_strategy == "subagent_per_claim" and cfg.steps["check"].kind == "agent"
    assert all(any(k.path == p for k in knobs) for p in ui.COUPLED)  # every coupled setting has a widget


def _random_value(knob, rng):
    """A value the user could set in this widget (benign free text; broken overrides are tested in test_config)."""
    c = knob.comp
    if isinstance(c, gr.Checkbox):
        return rng.random() < 0.5
    if isinstance(c, gr.Slider):
        return c.minimum + rng.randint(0, int(round((c.maximum - c.minimum) / c.step))) * c.step
    if isinstance(c, (gr.Radio, gr.Dropdown, gr.CheckboxGroup)):
        opts = ui._ids(c.choices)
        return rng.sample(opts, rng.randint(0, len(opts))) if isinstance(c, gr.CheckboxGroup) else rng.choice(opts)
    return rng.choice(["", "Ada Lovelace; Someone Else" if knob.extra else "a.com, b.org"
                       if knob.path[-1] == "blocked_domains" else "Check {{ text }}"
                       if knob.path[-1] == "prompt_override" else "Be terse."])


def test_random_widget_edits_never_produce_an_error(demo):
    """Random edit sequences from every preset, handled like the UI does, always give a valid, previewable config
    (a scratch fuzz of 4,500 such states found only broken prompt overrides, now rejected with a clear message)."""
    knobs, rng = demo.afc_knobs, random.Random(0)
    for start in [None, *C.list_presets()] * 6:
        vals = ui.values_from(knobs, C.load_preset(start) if start else C.FactCheckConfig())
        for _ in range(10):
            i = rng.randrange(len(knobs))
            vals[i] = _random_value(knobs[i], rng)
            if knobs[i].path in ui.COUPLED and not knobs[i].extra:
                vals = ui.fix_values(knobs, knobs[i].path, vals)[0]  # the .input/.select handler
            ui.preview(ui.cfg_from(knobs, vals), "TEXT")  # what Preview / Run / Save validate


def test_preview_shows_each_call_type():
    l3 = ui.preview(C.load_preset("L3_agent_subagents_claude"), "TEXT")
    assert "SUBAGENTS (--agents JSON)" in l3 and "claim-checker" in l3
    l5 = ui.preview(C.load_preset("L5_per_claim_x_scientist_calls"), "TEXT")
    assert "EXTRACT" in l5 and "PERSPECTIVE (Karl Popper)" in l5 and "<document_context>" in l5
    off = C.apply_overrides(C.load_preset("L5_per_claim_x_scientist_calls"), ["steps.perspective.enabled=false"])
    assert "PERSPECTIVE" not in ui.preview(off, "TEXT")  # a disabled perspective step makes no calls


def test_preview_disabled_extraction_matches_real_check():
    """Disabled extraction checks the actual whole input, with no invented extracted-claim context."""
    from auto_fact_checker.prompts import build_prompt

    cfg = C.apply_overrides(C.FactCheckConfig(), ["claim_strategy=separate_call_per_claim",
                                                 "steps.extract.enabled=false"])
    actual = build_prompt(cfg, "check", "TEXT")
    preview = ui.preview(cfg, "TEXT")
    assert "EXTRACT" not in preview and "<one extracted claim>" not in preview
    assert preview.split("########## CHECK ##########\n")[-1] == actual
    cfg.steps["extract"].enabled = True
    assert "illustrative" in ui.preview(cfg, "TEXT").lower()


def test_stop_keeps_polling_until_terminal_state(demo):
    """Stop signals workers immediately; cancelling the polling generator would freeze the status."""
    config = demo.get_config_file()
    stop_id = next(c["id"] for c in config["components"] if c.get("props", {}).get("value") == "Stop")
    events = [d for d in config["dependencies"] if [stop_id, "click"] in d["targets"]
              or (stop_id, "click") in d["targets"]]
    assert events and all(not e["cancels"] and e["queue"] is False for e in events)


def test_claim_widths_match_claims_table_columns():
    # ui.CLAIM_WIDTHS sizes the Claims Dataframe; a new render.claims_rows column needs a width too.
    from auto_fact_checker import render
    from auto_fact_checker.schema import FactCheckSummary

    rows = render.claims_rows(FactCheckSummary(claims=[{"claim": "c"}]))
    assert len(ui.CLAIM_WIDTHS) == len(rows[0])


def test_launch_without_blocking_serves_the_app():
    # block=False is what docs/scripts/take_screenshots.py uses to drive the real app from the same process.
    import socket
    import urllib.request

    with socket.socket() as s:  # port 0 asks the OS for a free port
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    demo = ui.launch(port=port, inbrowser=False, block=False)
    try:
        assert urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=30).status == 200
    finally:
        demo.close()


def test_stream_yields_final_outputs(fake):
    cfg = C.FactCheckConfig()
    run = new_run("Text", cfg)
    frames = list(ui._stream(run, ui.EXECUTOR.submit(run_fact_check, "Text", cfg, run)))
    final = frames[-1]
    assert len(final) == 13 and "**done**" in final[1] and final[6] == "Text [corrected]"


def test_status_discloses_unknown_costs(settings):
    """A missing price must not look like a complete zero-dollar measurement in the UI."""
    from auto_fact_checker import spend
    from auto_fact_checker.backends.base import LLMResult
    from auto_fact_checker.results import record_call

    run = new_run("Text", C.FactCheckConfig())
    result = LLMResult(backend="openai_api", model="unknown", cost_usd=None, billed=True)
    record_call(run, "check", "test", result)
    spend.record(settings.ledger, None, True, "test")
    status = ui.outputs_for(run)[1]
    assert "known estimate" in status and "1 unknown-cost calls" in status
    assert "1 unknown billed calls" in status
