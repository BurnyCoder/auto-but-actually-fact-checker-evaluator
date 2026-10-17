"""Tests for the `afc` CLI and the shipped presets (offline, fake backend).

Global context: presets are the "modes" users pick in the UI; every preset must load and run end to end.
"""

import pytest

from auto_fact_checker import config as C
from auto_fact_checker.__main__ import main

EXAMPLE = C.ROOT / "examples" / "ai_research.md"


@pytest.mark.parametrize("preset", C.list_presets())
def test_every_preset_runs_through_the_cli(fake, settings, preset):
    assert main(["check", str(EXAMPLE), "--preset", preset, "--set", "max_parallel=2"]) == 0
    reports = list(settings.runs_dir.glob("*/report.md"))
    assert len(reports) == 1 and "Iteration 1" in reports[0].read_text(encoding="utf-8")
    assert fake.requests  # at least one (fake) LLM call per preset


def test_spend_command(settings, capsys):
    assert main(["spend"]) == 0
    assert "Billed spend: $0.0000" in capsys.readouterr().out
