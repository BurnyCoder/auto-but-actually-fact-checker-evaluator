"""Offline checks of report evidence: partial credit, exclusions, missing logs and proposed-text trajectories.

Local purpose: protect the distinctions stated in the 2026-10-22 report corrections.
Global context: raw experiments remain immutable; these checks exercise post-hoc reporting only.
Sources: reports/scripts/exp08_posthoc.py and docs/correction_eval.md define the scored quantities.
"""

import importlib.util
import hashlib
import json
from pathlib import Path

import pytest


def report_module(name):
    """Load a report helper directly, without executing its file-writing entry point."""
    path = Path(__file__).resolve().parents[1] / "reports" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_evidence_matches_before_audit_hashes():
    """Scientific corrections change interpretation, never the original observations or annotations."""
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "reports/results/evidence_hashes_2026-10-22.json").read_text(encoding="utf-8"))
    assert len(manifest["files"]) == 30
    assert [item["path"] for item in manifest["files"]
            if hashlib.sha256((root / item["path"]).read_bytes()).hexdigest() != item["sha256"]] == []


def test_partial_credit_is_not_fully_corrected_fraction():
    """A hedge earns half credit but does not count as a restored fact."""
    summary = report_module("exp08_posthoc").fix_summary([1, 0.5, 0, None])
    assert summary == {"n_scored": 3, "n_missing": 1, "weighted_mean": 0.5,
                       "fully_corrected": 1, "fully_corrected_fraction": 1 / 3}


def test_lstm_sensitivity_excludes_only_the_ambiguous_annotation():
    """The frozen text and original scores remain untouched when one annotation is excluded."""
    posthoc = report_module("exp08_posthoc")
    records = posthoc.load("naive")
    sensitivity = posthoc.lstm_sensitivity(records)
    assert sensitivity["excluded"] == {"passage": "wikipedia-long_short-term_memory", "error_id": "3"}
    assert sensitivity["pass1"]["n_scored"] == 47
    assert sensitivity["pass1"]["weighted_mean"] == pytest.approx(45.5 / 47)
    assert sensitivity["pass1"]["fully_corrected"] == 44
    assert sensitivity["pass4"]["weighted_mean"] == pytest.approx(46 / 47)
    assert sum(len(posthoc.haiku(r, 1)["fix"]) for r in records) == 48


def test_missing_local_run_artifacts_are_reported(tmp_path):
    """A clean clone must not invent time or cost values when local-only logs are absent."""
    result = report_module("exp08_posthoc").per_pass([{"run_id": "not-published"}], runs_dir=tmp_path)
    assert result == {"available": False, "missing_run_ids": ["not-published"], "values": None}


def test_provenance_covers_every_flag_without_assuming_truth():
    """Each new classification needs sources and a reason; contradictory sources remain explicit."""
    posthoc = report_module("exp08_posthoc")
    provenance = posthoc.claim_provenance()
    assert set(provenance) == set(sum(posthoc.AUDIT.values(), []))
    assert provenance["N01"]["status"] == "conflicting_sources"
    assert provenance["R03"]["status"] == "unresolved"
    assert all(item["sources"] and item["reason"] for item in provenance.values())


def test_proposal_trajectory_preserves_missingness_and_is_not_returned_answer():
    """The historical figure follows proposed corrections, even if the loop returned its input."""
    analysis = report_module("analyze_correction")
    record = {"output_text": "accepted", "passes": [{"corrected_text": "proposal", "self_accuracy": 95}],
              "judged": [{"text": "accepted", "judges": {"haiku": {"correct": True}}},
                         {"text": "proposal", "judges": {"haiku": {"correct": None}}}]}
    curve = analysis.trajectory([record], "haiku", max_k=1)
    assert curve[0]["n"] == 1 and curve[0]["judge_correct"] == 1
    assert curve[1]["n"] == 0 and curve[1]["judge_correct"] is None
    assert analysis.verdict(record, record["output_text"], "haiku") is True


def test_scifact_figure_uses_even_sample_median(tmp_path, monkeypatch):
    """Two equally frequent values have their midpoint as median, not the upper observed value."""
    analysis = report_module("analyze_scifact")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    records = {i: {"label": i < 100, "p_true": (i % 100 >= 50)} for i in range(200)}
    monkeypatch.setattr(analysis, "FIG", tmp_path)
    # The bootstrap isn't under test; avoid 5,000 redundant metric computations on this plotting fixture.
    monkeypatch.setattr(analysis.metrics, "balanced_accuracy", lambda *args: .5)
    analysis.figures({"A_baseline": records}, {"systems": {"A_baseline": {"balanced_accuracy": .5}}})
    median_lines = [line for line in plt.gcf().axes[0].lines if line.get_color() == "#0b0b0b"]
    assert len(median_lines) == 2 and all(list(line.get_ydata()) == [50, 50] for line in median_lines)
    plt.close("all")


def test_multiple_gold_abstracts_are_preserved_in_judge_prompt():
    """The five multi-abstract Exp07 cases must render every supplied evidence document and sentence."""
    from auto_fact_checker.prompts import ENV

    path = Path(__file__).resolve().parents[1] / "reports/results/exp07_correction_codex/items.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    multiple = {r["id"]: r for r in records if len(r["meta"]["evidence"]) > 1}
    assert {key: len(r["meta"]["evidence"]) for key, r in multiple.items()} == {
        "train-531": 3, "train-1120": 3, "train-1181": 4, "validation-275": 2, "validation-70": 2}
    for record in multiple.values():
        prompt = ENV.get_template("judge/gold_evidence.md").render(
            text=record["text"], question=record["text"], evidence=record["meta"]["evidence"])
        for abstract in record["meta"]["evidence"]:
            assert abstract["title"] in prompt
            assert all(sentence in prompt for sentence in abstract["sentences"])
