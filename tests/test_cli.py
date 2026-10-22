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


def test_bench_command_passes_options(fake, settings, tmp_path, monkeypatch):
    from auto_fact_checker.bench import datasets
    from tests.test_bench import fake_parquet

    monkeypatch.setattr(datasets.pd, "read_parquet", fake_parquet)
    out = tmp_path / "b"
    assert main(["bench", "--splits", "validation", "--systems", str(C.ROOT / "configs/bench/baseline.json"),
                 "--n", "2", "--max-cost", "1", "--out", str(out)]) == 0
    assert (out / "summary.json").exists()


def test_spend_command(settings, capsys):
    assert main(["spend"]) == 0
    assert "Known billed estimate: $0.0000" in capsys.readouterr().out


def test_check_returns_nonzero_when_summary_is_unusable(fake):
    """Automation can distinguish an unusable model answer from a completed fact-check."""
    fake.__init__(no_json_for=["iter1/check"])
    assert main(["check", str(EXAMPLE), "--set", "steps.repair.enabled=false"]) == 1
