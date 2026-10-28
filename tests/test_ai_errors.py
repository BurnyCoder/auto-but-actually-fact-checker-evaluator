"""Tests for the AI-research error-injection benchmark (Exp08): source parsing, injection validation, reference
judge scoring and the forced-pass correction runner.

Global context: Exp08 corrupts real Wikipedia/arXiv passages with k known errors and scores every correction pass
against the original passage; these offline tests (fake backend, canned API responses) pin down each piece.
"""

import json

import pytest

from auto_fact_checker import config as C
from auto_fact_checker.bench import ai_errors, sources
from auto_fact_checker.bench.judge import judge_reference
from auto_fact_checker.schema import InjectedError, RefVerdict, parse_block

PASSAGE = "AlexNet was designed in 2012. It won the ImageNet challenge. It used GPUs. Its error rate was 15.3%."
WIKI_JSON = json.dumps({"query": {"pages": {"1": {"title": "AlexNet", "extract": "AlexNet is a CNN.\n\nIt won."}}}})
ARXIV_XML = ("<feed><title>arXiv query</title><entry><id>x</id><title>Attention Is\n All You Need</title>"
             "<summary>  The dominant sequence\n transduction models. </summary></entry></feed>")


def cfg(name):
    return C.load_preset(C.ROOT / "configs" / "bench" / f"{name}.json")


def test_sources_parse_wikipedia_and_arxiv(monkeypatch):
    monkeypatch.setattr(sources, "_get", lambda url: WIKI_JSON if "wikipedia" in url else ARXIV_XML)
    monkeypatch.setattr(sources, "ARXIV_DELAY_S", 0)
    w = sources.fetch_wikipedia_lead("AlexNet")
    assert w["text"] == "AlexNet is a CNN. It won." and w["url"].endswith("/wiki/AlexNet")
    a = sources.fetch_arxiv_abstract("1706.03762")
    assert a["title"] == "Attention Is All You Need" and a["text"] == "The dominant sequence transduction models."
    assert "@" not in sources.UA  # identify the project, never a personal address


def test_trim_keeps_whole_sentences_within_budget():
    assert sources.split_sentences(PASSAGE)[1] == "It won the ImageNet challenge."
    assert sources.trim_sentences(PASSAGE, max_words=12, min_sentences=1) == \
        "AlexNet was designed in 2012. It won the ImageNet challenge."
    assert len(sources.split_sentences(sources.trim_sentences(PASSAGE, max_words=1))) == 3  # min_sentences floor


def test_validate_keeps_only_small_distinct_edits_of_passage_sentences():
    e = lambda o, p: InjectedError(original_sentence=o, perturbed_sentence=p, false_fact="f", true_fact="t")  # noqa
    errors = [e("Not in the passage.", "x"),  # not a substring
              e("It used GPUs.", "It used GPUs."),  # unchanged
              e("It used GPUs.", "Completely different words that share nothing at all here."),  # rewrite
              e("AlexNet was designed in 2012.", "AlexNet was designed in 1998."),
              e("AlexNet was designed in 2012.", "AlexNet was designed in 2005."),  # same sentence twice
              e("It won the ImageNet challenge.", "It lost the ImageNet challenge."),
              e("It used GPUs.", "It used TPUs.")]  # beyond k
    out = ai_errors.validate(PASSAGE, errors, 2)
    assert [x["perturbed_sentence"] for x in out] == ["AlexNet was designed in 1998.", "It lost the ImageNet challenge."]
    assert [x["id"] for x in out] == [1, 2]
    snapped = ai_errors.validate(PASSAGE, [e("Its error rate was 15.3 %.", "Its error rate was 45.3%.")], 1)
    assert snapped[0]["original_sentence"] == "Its error rate was 15.3%."  # near-copy snapped to the real sentence
    assert ai_errors.perturb(PASSAGE, out).startswith("AlexNet was designed in 1998. It lost")


def test_ref_verdict_fix_scores():
    v = parse_block('```json\n{"errors": [{"id": 1, "status": "Corrected"}, {"id": 2, "status": "partially"}, '
                    '{"id": 3, "status": "uncorrected"}, {"id": 5, "status": "??"}], "overall_accuracy_pct": "85%"}\n```',
                    RefVerdict)
    assert v.fix_scores([1, 2, 3, 4, 5]) == {1: 1.0, 2: 0.5, 3: 0.0, 4: None, 5: None}
    assert v.overall_accuracy_pct == 85


def test_judge_reference_scores_against_original(fake, settings):
    errs = [{"id": 1, "false_fact": "1998", "true_fact": "2012", "perturbed_sentence": "designed in 1998."}]
    out = judge_reference("Text [corrected]", PASSAGE, errs, cfg("judge_luna"), "judge/luna/x/t1")
    assert out["overall"] == 100 and out["fix"] == {1: 1.0} and out["fix_mean"] == 1.0 and out["introduced"] == 0
    assert "[1] wrong: 1998 | true: 2012" in fake.requests[-1].prompt and fake.requests[-1].web_search is False
    bad = judge_reference("Unchanged text", PASSAGE, errs, cfg("judge_luna"), "judge/luna/x/t0")
    assert bad["overall"] == 40 and bad["fix_mean"] == 0.0


def test_build_injects_seeded_errors(fake, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(ai_errors, "WIKIPEDIA", ["A", "B"])
    monkeypatch.setattr(ai_errors, "ARXIV", ["1", "2"])
    monkeypatch.setattr(ai_errors, "KS", [0, 2])
    doc = lambda src, t: {"source": src, "title": t, "text": PASSAGE, "url": f"https://x/{t}", "license": "L"}  # noqa
    monkeypatch.setattr(sources, "fetch_wikipedia_lead", lambda t: doc("wikipedia", t))
    monkeypatch.setattr(sources, "fetch_arxiv_abstract", lambda a: doc("arxiv", a))
    rows = ai_errors.build(tmp_path, cfg("judge_luna"))
    assert sorted(r["k"] for r in rows[:2]) == sorted(r["k"] for r in rows[2:]) == [0, 2]  # balanced per source
    for r in rows:
        assert len(r["errors"]) == r["k"] and (r["perturbed"] == r["original"]) == (r["k"] == 0)
        assert all(e["perturbed_sentence"] in r["perturbed"] for e in r["errors"])
    assert len(ai_errors.load(tmp_path / "dataset.jsonl")) == 4


def test_build_requires_explicit_out(capsys):
    """A bare `afc ai-errors build` must not default to (and overwrite) the frozen benchmarks/ai_errors_v1."""
    with pytest.raises(SystemExit):
        ai_errors.main(["build"])
    assert "--out" in capsys.readouterr().err


def test_forced_passes_record_states_and_judgements(fake, settings):
    fake.__init__(accuracies=[50, 95, 95, 95])  # self-rated accurate from pass 2 on -> derived self-stop at pass 2
    errs = [{"id": 1, "error_type": "t", "original_sentence": "It used GPUs.", "perturbed_sentence": "It used TPUs.",
             "false_fact": "TPUs", "true_fact": "GPUs"}]
    row = {"id": "w", "source": "wikipedia", "url": "https://x/w", "k": 1, "original": PASSAGE,
           "perturbed": ai_errors.perturb(PASSAGE, errs), "errors": errs}
    item = ai_errors.BenchItem(id="w", text=row["perturbed"], label=1, meta=row)
    rec = ai_errors.ai_error_item(item, cfg("ai_rigorous_codex"), {"luna": cfg("judge_luna"), "haiku": cfg("judge_haiku")})
    assert rec["n_passes"] == 4 and rec["status"] == "done" and len(rec["state_text"]) == 5
    assert rec["texts"][0] == PASSAGE and rec["texts"][rec["state_text"][0]] == row["perturbed"]
    assert rec["texts"][rec["state_text"][4]].count("[corrected]") == 4  # each pass corrected the previous text
    assert rec["self_stop_pass"] == 2 and rec["self_stop_state"] == 1
    assert len(rec["judged"]) == len(rec["texts"]) == 6 and set(rec["judged"][0]) == {"luna", "haiku"}
    assert rec["judged"][0]["haiku"]["overall"] == 100  # the original is judged fully accurate
    assert rec["judged"][rec["state_text"][0]]["luna"]["fix"] == {1: 0.0}  # the corrupted input still has the error
    assert rec["errors"] == [] and rec["p_true"] == 0.5


def test_states_carry_forward_after_early_stop():
    ps = [{"corrected_text": "a", "input_text": "p"}, {"corrected_text": None, "input_text": "a"}]
    assert ai_errors.states(ps, "p") == ["p", "a", "a", "a", "a"]


def test_analysis_script_runs_on_runner_records(fake, settings):
    """The pre-registered analysis consumes exactly what the runner writes (after a JSON round trip)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("aa", C.ROOT / "reports" / "scripts" / "analyze_ai_errors.py")
    aa = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(aa)
    errs = [{"id": 1, "error_type": "wrong number or year", "original_sentence": "Its error rate was 15.3%.",
             "perturbed_sentence": "Its error rate was 45.3%.", "false_fact": "45.3%", "true_fact": "15.3%"}]
    rows = [{"id": "a", "source": "arxiv", "url": "u", "k": 1, "original": PASSAGE,
             "perturbed": ai_errors.perturb(PASSAGE, errs), "errors": errs},
            {"id": "b", "source": "wikipedia", "url": "u", "k": 0, "original": PASSAGE, "perturbed": PASSAGE,
             "errors": []}]
    judges = {"luna": cfg("judge_luna"), "haiku": cfg("judge_haiku")}
    arms = {a: [json.loads(json.dumps(ai_errors.ai_error_item(ai_errors.BenchItem(r["id"], r["perturbed"], r["k"], r),
                                                              cfg(f"ai_{a}_codex"), judges))) for r in rows]
            for a in ("naive", "rigorous")}
    res = aa.analyse({a: aa.attach_errors(recs, {r["id"]: r for r in rows}) for a, recs in arms.items()})
    rg = res["arms"]["rigorous"]
    assert [c["score_mean"] for c in rg["curve"]] == [70, 100, 100, 100, 100]  # (40 + 100) / 2 before correcting
    assert rg["curve"][0]["fix"]["mean"] == 0 and rg["curve"][1]["fix"]["mean"] == 1
    assert rg["H3_pass1_vs_perturbed"]["delta"] == 30 and rg["controls_k0"]["n"] == 1
    assert res["validity"]["haiku"]["original_mean_score"] == 100
    assert res["H2_rigorous_vs_naive_pass1"]["delta"] == 0
