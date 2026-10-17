"""Exp07 analysis: judge validity, H1-H3 and descriptive statistics of the correction loop (pre-registered in
docs/correction_eval.md; written before any Exp07 data existed).

Usage: uv run --group paper python reports/scripts/analyze_correction.py
Reads reports/results/exp07_*/loop_*.jsonl written by `afc correct-eval`, writes
reports/results/correction_analysis.json and reports/figures/fig3_correction_loop.{png,pdf}.
Statistics: exact McNemar (statsmodels, via bench.metrics.mcnemar_exact), Wilson CI (statsmodels), paired bootstrap of
a difference in proportions (Efron & Tibshirani 1993), Cohen's kappa (sklearn.metrics.cohen_kappa_score).
"""

import json
import random
from collections import Counter
from pathlib import Path

from sklearn.metrics import cohen_kappa_score
from statsmodels.stats.proportion import proportion_confint

from auto_fact_checker.bench import metrics

R = Path(__file__).resolve().parents[1] / "results"
FIG = Path(__file__).resolve().parents[1] / "figures"
ARMS = {"codex": (R / "exp07_correction_codex" / "loop_codex_search.jsonl", "haiku", "luna"),
        "claude": (R / "exp07_correction_claude" / "loop_claude_subagents.jsonl", "luna", "haiku")}
COLORS = {"judge": "#2a78d6", "self": "#eb6834"}  # dataviz reference slots 1-2


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def verdict(rec: dict, text: str | None, judge: str):
    """Judge correctness of one of the record's texts (None if missing/refused/not judged)."""
    for jt in rec["judged"]:
        if jt["text"] == text:
            return jt["judges"].get(judge, {}).get("correct")
    return None


def wilson(k: int, n: int) -> list:
    return list(proportion_confint(k, n, alpha=0.05, method="wilson")) if n else [None, None]


def boot_diff(a: list[bool], b: list[bool], n_boot: int = 10_000, seed: int = 0) -> list:
    """95% percentile CI of mean(b) - mean(a) resampling paired items."""
    rng, n = random.Random(seed), len(a)
    if n == 0:
        return [None, None]
    diffs = sorted(sum(b[i] - a[i] for i in idx) / n for idx in ([rng.randrange(n) for _ in range(n)]
                                                                   for _ in range(n_boot)))
    return [diffs[int(0.025 * n_boot)], diffs[int(0.975 * n_boot) - 1]]


def paired(recs, judge, first, second) -> dict:
    """Paired comparison of correctness of two texts per item (first -> second)."""
    pairs = [(verdict(r, first(r), judge), verdict(r, second(r), judge)) for r in recs]
    pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
    a, b = [x for x, _ in pairs], [y for _, y in pairs]
    out = {"n": len(pairs), "first_correct": sum(a), "second_correct": sum(b)}
    if pairs:
        out |= {"delta": (sum(b) - sum(a)) / len(pairs), "ci95": boot_diff(a, b), "mcnemar": metrics.mcnemar_exact(a, b)}
    return out


def first_correction(r):
    return next((p["corrected_text"] for p in r["passes"] if p["corrected_text"]), None)


def analyse(recs: list[dict], primary: str, secondary: str) -> dict:
    orig = lambda r: r["judged"][0]["text"]  # noqa: E731 - the original claim is always judged first
    out_ = lambda r: r["output_text"]  # noqa: E731
    res = {"n_items": len(recs), "primary_judge": primary, "secondary_judge": secondary}
    for j in (primary, secondary):  # judge validity on originals, where the truth is the gold label
        v = [(verdict(r, orig(r), j), r["label"]) for r in recs]
        ok = [c == g for c, g in v if c is not None]
        res[f"validity_{j}"] = {"n": len(ok), "missing": sum(c is None for c, _ in v), "accuracy": sum(ok) / len(ok)
                                if ok else None, "ci95": wilson(sum(ok), len(ok))}
    both = [(jt["judges"].get(primary, {}).get("correct"), jt["judges"].get(secondary, {}).get("correct"))
            for r in recs for jt in r["judged"]]
    both = [(a, b) for a, b in both if a is not None and b is not None]
    res["judge_agreement"] = {"n_texts": len(both), "agreement": sum(a == b for a, b in both) / len(both) if both
                              else None, "kappa": cohen_kappa_score([a for a, _ in both], [b for _, b in both])
                              if len({x for p in both for x in p}) > 1 else None}
    res["H1_original_to_output"] = paired(recs, primary, orig, out_)
    selfl = [verdict(r, out_(r), primary) for r in recs if r["self_labeled_correct"]]
    selfl = [v for v in selfl if v is not None]
    res["H2_self_label_precision"] = {"n_self_labelled": sum(r["self_labeled_correct"] for r in recs),
                                      "n_judged": len(selfl), "precision": sum(selfl) / len(selfl) if selfl else None,
                                      "ci95": wilson(sum(selfl), len(selfl))}
    res["H3_first_correction_to_output"] = paired([r for r in recs if first_correction(r)], primary,
                                                  first_correction, out_)
    false_ = [verdict(r, out_(r), primary) for r in recs if not r["label"]]
    false_ = [v for v in false_ if v is not None]
    res["repair_rate_false_originals"] = {"n": len(false_), "rate": sum(false_) / len(false_) if false_ else None,
                                         "ci95": wilson(sum(false_), len(false_))}
    good = [verdict(r, out_(r), primary) for r in recs if verdict(r, orig(r), primary) is True]
    good = [v for v in good if v is not None]
    res["harm_rate_correct_originals"] = {"n": len(good), "rate": sum(not v for v in good) / len(good) if good
                                          else None, "ci95": wilson(sum(not v for v in good), len(good))}
    res["passes"] = dict(sorted(Counter(r["n_passes"] for r in recs).items()))
    res["stop_reasons"] = dict(Counter((r["stop_reason"] or "").split(":")[0] for r in recs))
    res["self_labelled_share"] = sum(r["self_labeled_correct"] for r in recs) / len(recs) if recs else None
    res["by_gold"] = {g: {"n": sum(r["label"] == (g == "SUPPORT") for r in recs),
                          "output_correct": sum(verdict(r, out_(r), primary) is True for r in recs
                                                if r["label"] == (g == "SUPPORT"))} for g in ("SUPPORT", "CONTRADICT")}
    res["cost"] = {"billed_usd": sum(r["billed_usd"] for r in recs), "total_usd": sum(r["cost_usd"] for r in recs),
                   "searches": sum(r["searches"] for r in recs)}
    res["leak_items"] = sum(r["leak"] for r in recs)
    res["trajectory"] = trajectory(recs, primary)
    return res


def trajectory(recs, judge, max_k: int = 8) -> list[dict]:
    """State after k passes (k = 0: original), items carried forward after they stop (no survivorship bias)."""
    rows = []
    for k in range(max_k + 1):
        corr, selfs = [], []
        for r in recs:
            texts = [r["judged"][0]["text"]] + [p["corrected_text"] or None for p in r["passes"]]
            state = next(t for t in reversed(texts[: k + 1]) if t)  # last proposed text up to pass k
            v = verdict(r, state, judge)
            if v is not None:
                corr.append(v)
            if k < len(r["passes"]) and r["passes"][k]["self_accuracy"] is not None:
                selfs.append(r["passes"][k]["self_accuracy"] / 100)
        rows.append({"k": k, "n": len(corr), "judge_correct": sum(corr) / len(corr) if corr else None,
                     "self_accuracy_of_input": sum(selfs) / len(selfs) if selfs else None, "n_self": len(selfs)})
    return rows


def figure(results: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    arms = [a for a in results if results[a]["n_items"] >= 10]  # tiny arms are reported in text, not plotted
    if not arms:
        return
    FIG.mkdir(exist_ok=True)
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, len(arms), figsize=(4.2 * len(arms), 2.8), squeeze=False, sharey=True)
    for ax, arm in zip(axes[0], arms):
        tr = [t for t in results[arm]["trajectory"] if t["judge_correct"] is not None]
        ax.plot([t["k"] for t in tr], [t["judge_correct"] for t in tr], "-o", color=COLORS["judge"], ms=5,
                label=f"judged correct by gold evidence ({results[arm]['primary_judge']})")
        st = [t for t in results[arm]["trajectory"] if t["self_accuracy_of_input"] is not None]
        ax.plot([t["k"] for t in st], [t["self_accuracy_of_input"] for t in st], "-s", color=COLORS["self"], ms=4,
                label="loop's own accuracy rating of the text it checks")
        ax.set_title(f"{arm} loop (n = {results[arm]['n_items']})", fontsize=9)
        ax.set_xlabel("passes completed (0 = original claim; stopped items carried forward)")
        ax.set_ylim(0, 1.02)
    axes[0][0].set_ylabel("share / mean (0-1)")
    axes[0][0].legend(fontsize=7, loc="lower right", frameon=False)
    fig.savefig(FIG / "fig3_correction_loop.png", dpi=200, bbox_inches="tight")
    fig.savefig(FIG / "fig3_correction_loop.pdf", bbox_inches="tight")


def main() -> None:
    results = {arm: analyse(load(path), primary, secondary) for arm, (path, primary, secondary) in ARMS.items()}
    (R / "correction_analysis.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(json.dumps(results, indent=1))
    figure(results)


if __name__ == "__main__":
    main()
