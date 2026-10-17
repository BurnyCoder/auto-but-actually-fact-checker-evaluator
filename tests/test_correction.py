"""Tests for the correction-loop evaluation (Exp07): gold evidence join, gold-evidence judge, correction runner.

Global context: Exp07 asks whether texts that the iterate-until-accurate loop labels "correct" are correct by an
independent judge grounded in SciFact's gold abstracts; these offline tests (fake backend) pin down the data join,
the judge contract and what the runner records for every pass.
"""

import json

import pandas as pd
import pytest

from auto_fact_checker import config as C
from auto_fact_checker.bench import correction, datasets
from auto_fact_checker.bench.judge import judge
from auto_fact_checker.schema import JudgeVerdict, parse_block

CLAIMS = pd.DataFrame([(1, "c1", "7", "SUPPORT", [0, 2]), (2, "c2", "8", "CONTRADICT", [1]), (3, "c3", "", "", [])],
                      columns=["id", "claim", "evidence_doc_id", "evidence_label", "evidence_sentences"])
CORPUS = pd.DataFrame([(7, "Paper seven", ["s0", "s1", "s2"]), (8, "Paper eight", ["t0", "t1"])],
                      columns=["doc_id", "title", "abstract"])


def fake_read(url):
    return CORPUS if "corpus" in url else CLAIMS


def test_scifact_items_carry_gold_evidence(monkeypatch):
    monkeypatch.setattr(datasets.pd, "read_parquet", fake_read)
    items = {i.id: i for i in datasets.load_scifact(("validation",), with_evidence=True)}
    assert set(items) == {"validation-1", "validation-2"}  # NEI claim 3 dropped as before
    ev = items["validation-1"].meta["evidence"]
    assert ev == [{"title": "Paper seven", "sentences": ["s0", "s1", "s2"], "evidence_idx": [0, 2]}]
    assert "evidence" not in datasets.load_scifact(("validation",))[0].meta  # opt-in: no corpus download by default


def test_judge_verdict_correctness_rule():
    v = parse_block('```json\n{"main_claim_entailed": "true", "contradicts_evidence": false, '
                    '"same_question": true}\n```', JudgeVerdict)
    assert v.correct() is True
    assert JudgeVerdict(main_claim_entailed=True, contradicts_evidence=False, same_question=False).correct() is False
    assert JudgeVerdict(main_claim_entailed=True).correct() is None  # incomplete verdict = missing, not wrong


def judge_cfg():
    return C.load_preset(C.ROOT / "configs" / "bench" / "judge_luna.json")


def test_judge_uses_gold_evidence_and_ledger(fake, settings):
    ev = [{"title": "Paper seven", "sentences": ["alpha", "beta"], "evidence_idx": [1]}]
    out = judge("X [corrected]", "original claim", ev, judge_cfg(), "judge/luna/item1/t0")
    prompt = fake.requests[-1].prompt
    assert "[1] (EVIDENCE) beta" in prompt and "original claim" in prompt and fake.requests[-1].web_search is False
    assert out["correct"] is True and out["error"] is None
    assert json.loads(settings.ledger.read_text(encoding="utf-8").splitlines()[-1])["label"] == "judge/luna/item1/t0"


def test_correction_item_records_passes_and_self_labelled_output(fake, settings):
    fake.__init__(accuracies=[20, 95])  # pass 1 flags the claim, pass 2 rates the correction accurate -> self-stop
    item = datasets.BenchItem(id="validation-2", text="Claim two.", label=False,
                              meta={"evidence": [{"title": "T", "sentences": ["e"], "evidence_idx": [0]}]})
    loop = C.FactCheckConfig(iterate_until_accurate=True, max_iterations=20, accuracy_threshold=90)
    rec = correction.correction_item(item, loop, {"luna": judge_cfg()})
    assert rec["n_passes"] == 2 and rec["self_labeled_correct"] is True
    assert rec["output_text"] == "Claim two. [corrected]"  # the input of the last pass is what got labelled correct
    texts = [j["text"] for j in rec["judged"]]
    assert texts[0] == "Claim two." and "Claim two. [corrected]" in texts and len(texts) == len(set(texts))
    original, output = rec["judged"][0]["judges"]["luna"], next(j for j in rec["judged"]
                                                                 if j["text"] == rec["output_text"])["judges"]["luna"]
    assert original["correct"] is False and output["correct"] is True
    assert [p["self_accuracy"] for p in rec["passes"]] == [20, 95] and rec["status"] == "done"


def test_correct_eval_cli_is_resumable(fake, settings, tmp_path, monkeypatch):
    from auto_fact_checker.__main__ import main

    monkeypatch.setattr(datasets.pd, "read_parquet", fake_read)
    items = tmp_path / "items.json"
    items.write_text(json.dumps([{"id": "validation-2"}, {"id": "validation-1"}]), encoding="utf-8")
    loop = tmp_path / "loop.json"
    loop.write_text('{"iterate_until_accurate": true, "max_iterations": 3}', encoding="utf-8")
    out = tmp_path / "out"
    args = ["correct-eval", "--splits", "validation", "--items-from", str(items), "--system", str(loop),
            "--judges", str(C.ROOT / "configs/bench/judge_luna.json"), "--out", str(out), "--max-cost", "1"]
    assert main(args) == 0
    lines = (out / "loop.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["id"] for line in lines] == ["validation-2", "validation-1"] or len(lines) == 2
    n = len(fake.requests)
    assert main(args) == 0 and len(fake.requests) == n  # cached


def test_analysis_on_synthetic_records():
    import importlib.util

    spec = importlib.util.spec_from_file_location("ac", C.ROOT / "reports" / "scripts" / "analyze_correction.py")
    ac = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ac)

    def rec(label, orig_ok, out_ok, selfl):
        j = lambda ok: {"haiku": {"correct": ok}, "luna": {"correct": ok}}  # noqa: E731
        return {"label": label, "self_labeled_correct": selfl, "output_text": "out", "n_passes": 2,
                "stop_reason": "all claims >= 90% accurate", "billed_usd": 0.001, "cost_usd": 0.01, "searches": 1,
                "leak": False, "passes": [{"corrected_text": "out", "self_accuracy": 95}],
                "judged": [{"text": "orig", "judges": j(orig_ok)}, {"text": "out", "judges": j(out_ok)}]}

    recs = [rec(False, False, True, True)] * 6 + [rec(True, True, True, True)] * 3 + [rec(True, True, False, True)]
    res = ac.analyse(recs, "haiku", "luna")
    assert res["validity_haiku"]["accuracy"] == 1.0  # judge reproduces gold on originals
    assert res["H1_original_to_output"]["mcnemar"]["c"] == 6 and res["H1_original_to_output"]["mcnemar"]["b"] == 1
    assert res["H2_self_label_precision"]["precision"] == 0.9 and res["repair_rate_false_originals"]["rate"] == 1.0
    assert res["harm_rate_correct_originals"]["rate"] == 0.25 and res["trajectory"][0]["judge_correct"] == 0.4


def test_single_pass_policy_matches_one_agent_call():
    import importlib.util
    import sys

    sys.path.insert(0, str(C.ROOT / "reports" / "scripts"))
    spec = importlib.util.spec_from_file_location("cvc", C.ROOT / "reports" / "scripts" / "compare_verdict_correction.py")
    cvc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cvc)
    rec = {"judged": [{"text": "orig"}], "passes": [{"all_accurate": False, "corrected_text": "fixed"}]}
    assert cvc.single_pass(rec) == "fixed"  # pass 1 flagged it -> its correction is the single-pass answer
    rec["passes"][0]["all_accurate"] = True
    assert cvc.single_pass(rec) == "orig"  # pass 1 rated it accurate -> keep the original
