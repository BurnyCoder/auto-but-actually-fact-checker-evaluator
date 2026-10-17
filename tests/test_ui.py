"""Tests for ui.py: the app builds, every config field round-trips through its widgets, previews and streaming work.

Global context: the UI must expose every FactCheckConfig knob (per step and global) and reproduce presets exactly,
otherwise "modes are presets over granular settings" would silently drop settings.
"""

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


def test_preview_shows_each_call_type():
    l3 = ui.preview(C.load_preset("L3_agent_subagents_claude"), "TEXT")
    assert "SUBAGENTS (--agents JSON)" in l3 and "claim-checker" in l3
    l5 = ui.preview(C.load_preset("L5_per_claim_x_scientist_calls"), "TEXT")
    assert "EXTRACT" in l5 and "PERSPECTIVE (Karl Popper)" in l5 and "<document_context>" in l5


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
