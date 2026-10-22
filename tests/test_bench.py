"""Tests for bench/: SciFact loading/sampling, metrics against hand-computed values, and the resumable runner.

Global context: experiment reports quote these metrics (balanced accuracy, Wilson CIs, McNemar, paired bootstrap),
so they are checked against independent computations here before any paid benchmark run.
"""

import json

import pandas as pd
import pytest

from auto_fact_checker.bench import datasets, metrics
from auto_fact_checker.bench import run as bench_run


def fake_parquet(url):
    rows = [  # claim 1: SUPPORT (two evidence rows), 2: CONTRADICT, 3: NEI, 4: conflicting, 5/6 SUPPORT/CONTRADICT
        (1, "c1", "SUPPORT"), (1, "c1", "SUPPORT"), (2, "c2", "CONTRADICT"), (3, "c3", ""),
        (4, "c4", "SUPPORT"), (4, "c4", "CONTRADICT"), (5, "c5", "SUPPORT"), (6, "c6", "CONTRADICT")]
    return pd.DataFrame(rows, columns=["id", "claim", "evidence_label"])


def test_scifact_binary_and_balanced_sampling(monkeypatch):
    monkeypatch.setattr(datasets.pd, "read_parquet", fake_parquet)
    items = datasets.load_scifact(splits=("validation",))
    assert {(i.id, i.label) for i in items} == {("validation-1", True), ("validation-2", False),
                                                ("validation-5", True), ("validation-6", False)}
    s1 = datasets.sample_balanced(items, 4, seed=0)
    assert sorted(i.label for i in s1) == [False, False, True, True]
    assert [i.id for i in datasets.sample_balanced(items, 4, seed=0)] == [i.id for i in s1]  # seeded
    rest = datasets.sample_balanced(items, 2, seed=1, exclude_ids={"validation-1", "validation-2"})
    assert {i.id for i in rest} == {"validation-5", "validation-6"}


def test_metrics_known_values():
    y = [True, True, True, False]
    p = [0.9, 0.6, 0.2, 0.1]  # predictions T, T, F, F -> 3/4 correct
    m = metrics.binary_metrics(y, p)
    assert m["accuracy"] == pytest.approx(0.75) and m["balanced_accuracy"] == pytest.approx((2 / 3 + 1) / 2)
    assert m["auroc"] == pytest.approx(1.0)  # every positive scores above the negative
    assert m["brier"] == pytest.approx(((0.1) ** 2 + 0.4 ** 2 + 0.8 ** 2 + 0.1 ** 2) / 4)
    lo, hi = m["accuracy_ci"]
    assert 0.2 < lo < 0.75 < hi < 1.0  # Wilson interval around 3/4
    assert metrics.balanced_accuracy(y, p) == pytest.approx(m["balanced_accuracy"])  # == sklearn's value
    missing = metrics.binary_metrics([True, False], [None, 0.2])
    assert missing["accuracy"] == 0.5 and missing["parse_fail"] == 1  # unparsed counts as wrong


def test_mcnemar_and_bootstrap():
    a = [True] * 10 + [False] * 10
    b = [True] * 10 + [True] * 8 + [False] * 2  # b fixes 8 of a's errors, breaks none
    res = metrics.mcnemar_exact(a, b)
    assert (res["b"], res["c"]) == (0, 8) and res["pvalue"] == pytest.approx(2 * 0.5 ** 8)  # exact binomial
    y = [True, False] * 10
    pa, pb = [0.5] * 20, [0.9 if t else 0.1 for t in y]
    delta, lo, hi = metrics.paired_bootstrap(y, pa, pb, metrics.balanced_accuracy, n_boot=500, seed=0)
    assert delta == pytest.approx(0.5) and lo > 0  # perfect vs chance-level system


def test_runner_caches_and_respects_cost_cap(fake, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(datasets.pd, "read_parquet", fake_parquet)
    sysdir = tmp_path / "systems"
    sysdir.mkdir()
    (sysdir / "a.json").write_text('{"steps": {"check": {"web_search": false}}}', encoding="utf-8")
    (sysdir / "b.json").write_text("{}", encoding="utf-8")
    out = tmp_path / "out"
    args = ["--dataset", "scifact", "--splits", "validation", "--systems", str(sysdir / "a.json"),
            str(sysdir / "b.json"), "--n", "4", "--out", str(out), "--max-cost", "1", "--workers", "2"]
    assert bench_run.main(args) == 0
    lines = (out / "a.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4 and json.loads(lines[0])["p_true"] == 0.8  # fake answers 80% accurate
    n_calls = len(fake.requests)
    assert bench_run.main(args) == 0 and len(fake.requests) == n_calls  # cached: no new calls on resume
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["systems"]["b"]["n"] == 4 and "a_vs_b" in summary["comparisons"]
    assert (out / "results.md").exists()
    capped = ["--max-cost", "0.0015", "--n", "4", "--workers", "1"]
    out2 = tmp_path / "out2"
    bench_run.main(["--dataset", "scifact", "--splits", "validation", "--systems", str(sysdir / "a.json"),
                    "--out", str(out2)] + capped)
    assert len((out2 / "a.jsonl").read_text(encoding="utf-8").splitlines()) < 4  # stopped by the cost cap


def test_failed_items_are_not_cached_and_summary_survives_missing_system(fake, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(datasets.pd, "read_parquet", fake_parquet)
    original = fake.__call__

    def flaky(req, log):  # every call on claim c1 fails like a network error
        res = original(req, log)
        if "c1" in req.prompt:
            res.error, res.text = "ConnectionError", ""
        return res

    monkeypatch.setattr(type(fake), "__call__", lambda self, req, log: flaky(req, log))
    sysfile = tmp_path / "a.json"
    sysfile.write_text("{}", encoding="utf-8")
    out = tmp_path / "out"
    args = ["--splits", "validation", "--systems", str(sysfile), str(tmp_path / "missing_b.json"), "--n", "4",
            "--out", str(out), "--max-cost", "1"]
    (tmp_path / "missing_b.json").write_text('{"max_cost_usd": 0.0}', encoding="utf-8")  # b never completes
    assert bench_run.main(args) == 0
    cached = [json.loads(line)["id"] for line in (out / "a.jsonl").read_text(encoding="utf-8").splitlines()]
    assert "validation-1" not in cached and len(cached) == 3  # the failed item will be retried on resume
    assert json.loads((out / "summary.json").read_text(encoding="utf-8"))["comparisons"] == {}


@pytest.mark.parametrize("refusal", [False, True])
def test_completed_unusable_answers_still_cache_as_wrong(fake, tmp_path, monkeypatch, refusal):
    """Parse failures/refusals stay wrong on resume, rather than being resampled until successful."""
    from auto_fact_checker import config as C

    original = type(fake).__call__

    def unusable(self, req, log):
        result = original(self, req, log)
        result.text = "I cannot provide this answer." if refusal else "No JSON answer."
        result.error = "refusal: model declined" if refusal else None
        return result

    monkeypatch.setattr(type(fake), "__call__", unusable)
    cfg = C.FactCheckConfig()
    cfg.steps["repair"].enabled = False
    item = datasets.BenchItem(id="example", text="Text", label=True)
    for _ in range(2):
        bench_run.run_system("test", cfg, [item], tmp_path, 1, [0.0], 1, lambda _: None)
    records = [json.loads(line) for line in (tmp_path / "test.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1 and len(fake.requests) == 1
    assert records[0]["status"] == "error" and records[0]["p_true"] is None
    assert metrics.predictions([True], [records[0]["p_true"]]) == [False]
