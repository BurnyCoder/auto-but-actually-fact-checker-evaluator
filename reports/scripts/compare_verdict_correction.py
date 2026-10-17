"""Post-hoc comparisons on the 100 Exp07 claims (decided after seeing Exp07; exploratory, not pre-registered).

Usage: uv run --group paper python reports/scripts/compare_verdict_correction.py
1. Verdict accuracy ("is the claim true?") of every system on the same 100 claims: A/B/C/D (Exp01-03), the first
   pass of the Exp07 Codex loop, and the Haiku judge that is given the gold abstract; plus the first-40 subset with
   the agent arms E (Exp04) and F (Exp05) and the E vs Exp07-pass-1 agreement (same configuration, independent runs).
2. Correction accuracy (is the produced text correct per the gold abstract?): original -> one agent pass
   (keep the original if pass 1 rates it >= 90%, else use pass 1's correction) -> full loop answer, with both judges,
   by gold class, detection vs repair, and cost/time per claim.
Reuses the pre-registered helpers in analyze_correction.py (verdict, paired, load) so definitions are identical.
Writes reports/results/verdict_vs_correction_posthoc.json.
"""

import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling script with the pre-registered helpers
import analyze_correction as ac  # noqa: E402

from auto_fact_checker.bench import metrics  # noqa: E402
from auto_fact_checker.config import get_settings  # noqa: E402
from auto_fact_checker.results import FactCheckRun  # noqa: E402

R = Path(__file__).resolve().parents[1] / "results"
SYSTEMS = {"A simple call, no search": "exp01/baseline.jsonl", "D full prompt, no search": "exp03_full_no_search/full_no_search.jsonl",
           "B full prompt + API search": "exp01/full_single_openai.jsonl", "C simple prompt + API search": "exp02/baseline_search.jsonl",
           "E Codex agent, full prompt (Exp04)": "exp04_codex_agent/full_agent_codex.jsonl",
           "F Claude Code agent, full prompt (Exp05)": "exp05_claude_agent/full_agent_claude.jsonl"}


def by_id(path: Path) -> dict:
    return {r["id"]: r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines())}


def verdict_stats(recs: dict, ids: list[str]) -> dict:
    """Verdict metrics (SUPPORT iff p_true >= 0.5) on the given claims."""
    ids = [i for i in ids if i in recs]
    y, p = [recs[i]["label"] for i in ids], [recs[i]["p_true"] for i in ids]
    pred = metrics.predictions(y, p)
    m = metrics.binary_metrics(y, p)
    return {"n": len(ids), "balanced_accuracy": m["balanced_accuracy"], "accuracy": m["accuracy"], "auroc": m["auroc"],
            "support_recall": sum(a for a, t in zip(pred, y) if t) / max(sum(y), 1),
            "contradict_recall": sum(not a for a, t in zip(pred, y) if not t) / max(sum(not t for t in y), 1)}


def single_pass(r: dict) -> str:
    """One agent call: keep the original if pass 1 rated it >= threshold (all accurate), else take its correction."""
    p = r["passes"][0]
    return r["judged"][0]["text"] if p["all_accurate"] or not p["corrected_text"] else p["corrected_text"]


def main() -> None:
    loop = ac.load(ac.ARMS["codex"][0])
    x7 = {r["id"]: r for r in loop}
    ids = list(x7)
    ids40 = [i["id"] for i in json.loads((R / "exp04_codex_agent" / "items.json").read_text(encoding="utf-8"))]
    systems = {name: by_id(R / path) for name, path in SYSTEMS.items()}
    systems["Exp07 pass 1: Codex agent, full prompt"] = x7
    out = {"note": "post hoc (after Exp07); exploratory",
           "verdict_100": {n: verdict_stats(s, ids) for n, s in systems.items() if not n.startswith(("E ", "F "))},
           "verdict_first40": {n: verdict_stats(s, ids40) for n, s in systems.items()}}
    e = systems["E Codex agent, full prompt (Exp04)"]
    ov = [i for i in ids40 if i in e and i in x7]
    pe = metrics.predictions([e[i]["label"] for i in ov], [e[i]["p_true"] for i in ov])
    p7 = metrics.predictions([x7[i]["label"] for i in ov], [x7[i]["p_true"] for i in ov])
    out["E_vs_exp07_pass1_agreement"] = {"n": len(ov), "same_prediction": sum(a == b for a, b in zip(pe, p7))}
    jv = [(ac.verdict(r, r["judged"][0]["text"], "haiku"), r["label"]) for r in loop]
    jv = [(c, g) for c, g in jv if c is not None]
    out["verdict_100"]["Haiku judge given the gold abstract"] = verdict_stats(
        {str(k): {"label": g, "p_true": 1.0 if c else 0.0} for k, (c, g) in enumerate(jv)}, [str(k) for k in range(len(jv))])
    orig = lambda r: r["judged"][0]["text"]  # noqa: E731
    final = lambda r: r["output_text"]  # noqa: E731
    out["correction"] = {}
    for j in ("haiku", "luna"):
        out["correction"][j] = {"original_to_single_pass": ac.paired(loop, j, orig, single_pass),
                                "single_pass_to_loop": ac.paired(loop, j, single_pass, final),
                                "original_to_loop": ac.paired(loop, j, orig, final)}
    out["loop_equals_single_pass"] = sum(single_pass(r) == r["output_text"] for r in loop)
    out["by_gold_haiku"] = {name: {"n": len(sub), "single_pass_correct": sum(ac.verdict(r, single_pass(r), "haiku") is True for r in sub),
                                   "loop_correct": sum(ac.verdict(r, final(r), "haiku") is True for r in sub)}
                            for name, sub in (("false claims", [r for r in loop if not r["label"]]),
                                              ("true claims", [r for r in loop if r["label"]]))}
    flagged = [r for r in loop if not r["label"] and r["p_true"] is not None and r["p_true"] < 0.5]
    out["false_claims_detection_vs_repair"] = {
        "false_claims": sum(not r["label"] for r in loop), "flagged_by_pass1_verdict": len(flagged),
        "flagged_and_repaired_by_loop": sum(ac.verdict(r, final(r), "haiku") is True for r in flagged)}
    true_ = [r for r in loop if r["label"]]
    out["true_claims_threshold"] = {"n": len(true_), "pass1_p_true_ge_0.5": sum((r["p_true"] or 0) >= 0.5 for r in true_),
                                    "pass1_rated_ge_threshold_kept": sum(r["passes"][0]["all_accurate"] for r in true_)}
    runs = get_settings().runs_dir
    c1, call, d1, dall = [], [], [], []
    for r in loop:
        run = FactCheckRun.model_validate_json((runs / r["run_id"] / "run.json").read_text(encoding="utf-8"))
        first = [c for c in run.calls if c.label.startswith("iter1/")]
        c1.append(sum(c.cost_usd or 0 for c in first))
        call.append(sum(c.cost_usd or 0 for c in run.calls))
        d1.append(sum(c.duration_s for c in first))
        dall.append(sum(c.duration_s for c in run.calls))
    out["cost_time_per_claim"] = {"single_pass_usd_notional": st.mean(c1), "loop_usd_notional": st.mean(call),
                                  "single_pass_s": st.mean(d1), "loop_s": st.mean(dall)}
    out["loop_final_self_label_true"] = sum(r["self_labeled_correct"] for r in loop)
    (R / "verdict_vs_correction_posthoc.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
