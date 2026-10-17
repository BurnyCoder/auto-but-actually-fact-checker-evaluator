"""Analysis of the SciFact experiments (Exp01 primary, Exp02 secondary, baseline test-retest) and paper figures.

Usage: uv run --group paper python reports/scripts/analyze_scifact.py
Reads the cached per-item records written by `afc bench` (reports/results/exp01, exp02, exp01_retest), computes
the pre-registered metrics/tests (docs/benchmark.md) for every system and every pairwise comparison, the
test-retest agreement of the baseline, per-class recalls, and two sensitivity analyses (excluding parse failures;
excluding leak-flagged items). Writes reports/results/scifact_analysis.json and figures in reports/figures/.
"""

import json
from pathlib import Path

from auto_fact_checker.bench import metrics

R = Path(__file__).resolve().parents[1] / "results"
FIG = Path(__file__).resolve().parents[1] / "figures"
SYSTEMS = {"A_baseline": R / "exp01" / "baseline.jsonl", "B_full": R / "exp01" / "full_single_openai.jsonl",
           "C_baseline_search": R / "exp02" / "baseline_search.jsonl",
           "A_retest": R / "exp01_retest" / "baseline_retest.jsonl"}
COLORS = {"A_baseline": "#2a78d6", "B_full": "#eb6834", "C_baseline_search": "#1baf7a"}  # dataviz slots 1-3


def load(path: Path) -> dict:
    return {r["id"]: r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines())} if path.exists() else {}


def recalls(y, p) -> dict:
    pred = metrics.predictions(y, p)
    out = {}
    for cls, name in ((True, "SUPPORT_recall"), (False, "CONTRADICT_recall")):
        idx = [i for i, t in enumerate(y) if t == cls]
        out[name] = sum(pred[i] == cls for i in idx) / len(idx) if idx else None
    return out


def compare(y, pa, pb) -> dict:
    ca = [x == t for x, t in zip(metrics.predictions(y, pa), y)]
    cb = [x == t for x, t in zip(metrics.predictions(y, pb), y)]
    d, lo, hi = metrics.paired_bootstrap(y, pa, pb, metrics.balanced_accuracy, n_boot=10_000, seed=0)
    return {"n": len(y), "delta_balanced_accuracy": d, "ci95": [lo, hi], "mcnemar": metrics.mcnemar_exact(ca, cb)}


def main() -> None:
    recs = {k: load(v) for k, v in SYSTEMS.items()}
    main_sys = ["A_baseline", "B_full", "C_baseline_search"]
    common = sorted(set.intersection(*(set(recs[s]) for s in main_sys if recs[s])))
    y = [recs["A_baseline"][i]["label"] for i in common]
    p = {s: [recs[s][i]["p_true"] for i in common] for s in main_sys if recs[s]}
    out = {"n_common": len(common), "systems": {}, "comparisons": {}, "sensitivity": {}}
    for s, ps in p.items():
        m = metrics.binary_metrics(y, ps) | recalls(y, ps)
        m["cost_usd"] = sum(recs[s][i]["cost_usd"] for i in common)
        m["mean_searches"] = sum(recs[s][i]["searches"] for i in common) / len(common)
        m["leak_items"] = sum(recs[s][i]["leak"] for i in common)
        out["systems"][s] = m
    pairs = [("A_baseline", "B_full"), ("A_baseline", "C_baseline_search"), ("C_baseline_search", "B_full")]
    for a, b in pairs:
        if a in p and b in p:
            out["comparisons"][f"{b}_minus_{a}"] = compare(y, p[a], p[b])
    # Sensitivity 1: drop items where any system failed to produce a parseable score.
    ok = [k for k, i in enumerate(common) if all(p[s][k] is not None for s in p)]
    # Sensitivity 2: drop items whose consulted sources hit a blocked/dataset host (possible label leakage).
    clean = [k for k, i in enumerate(common) if not any(recs[s][i]["leak"] for s in p)]
    for name, keep in (("parse_ok_only", ok), ("no_leak_flag", clean)):
        ys = [y[k] for k in keep]
        out["sensitivity"][name] = {"n": len(keep), **{f"{b}_minus_{a}": compare(ys, [p[a][k] for k in keep],
                                                                                [p[b][k] for k in keep])
                                                       for a, b in pairs if a in p and b in p}}
    # Test-retest of the baseline: same items, same config, independent second run.
    if recs["A_retest"]:
        both = [i for i in common if i in recs["A_retest"]]
        y2 = [recs["A_baseline"][i]["label"] for i in both]
        a1 = metrics.predictions(y2, [recs["A_baseline"][i]["p_true"] for i in both])
        a2 = metrics.predictions(y2, [recs["A_retest"][i]["p_true"] for i in both])
        out["test_retest"] = {"n": len(both), "prediction_agreement": sum(x == z for x, z in zip(a1, a2)) / len(both),
                              "retest_metrics": metrics.binary_metrics(y2, [recs["A_retest"][i]["p_true"]
                                                                            for i in both]),
                              "retest_vs_original": compare(y2, [recs["A_baseline"][i]["p_true"] for i in both],
                                                            [recs["A_retest"][i]["p_true"] for i in both])}
    (R / "scifact_analysis.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    figures(y, p, out)


def figures(y, p, out) -> None:
    """Fig 1: balanced accuracy with paired-bootstrap-free percentile CIs per system; Fig 2: p_true by gold class."""
    import random

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(exist_ok=True)
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    names = list(p)
    labels = {"A_baseline": "A: simple call", "B_full": "B: full prompt + search", "C_baseline_search": "C: simple call + search"}
    rng = random.Random(0)
    fig, ax = plt.subplots(figsize=(4.2, 2.2))
    for k, s in enumerate(names):  # percentile bootstrap CI of each system's balanced accuracy (item resampling)
        boots = []
        for _ in range(5000):
            idx = [rng.randrange(len(y)) for _ in y]
            boots.append(metrics.balanced_accuracy([y[i] for i in idx], [p[s][i] for i in idx]))
        boots.sort()
        est = out["systems"][s]["balanced_accuracy"]
        lo, hi = boots[125], boots[4874]
        ax.plot([lo, hi], [k, k], color=COLORS[s], lw=2, solid_capstyle="round")
        ax.plot([est], [k], "o", color=COLORS[s], ms=8, mec="white", mew=2)
        ax.text(hi + 0.01, k, f"{est:.3f} [{lo:.3f}, {hi:.3f}]", va="center", fontsize=8, color="#52514e")
    ax.axvline(0.5, color="#a3a29c", lw=1, ls=":")
    ax.set_yticks(range(len(names)), [labels[s] for s in names])
    ax.set_xlim(0.45, 1.05)
    ax.set_xlabel(f"balanced accuracy (n = {len(y)}, 95% bootstrap CI; dotted = chance)")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(FIG / "fig1_balanced_accuracy.png", dpi=200)
    fig.savefig(FIG / "fig1_balanced_accuracy.pdf")

    fig, axes = plt.subplots(1, len(names), figsize=(6.4, 2.3), sharey=True)
    for ax, s in zip(axes, names):
        for g, gold in enumerate((True, False)):
            vals = [100 * v for v, t in zip(p[s], y) if t == gold and v is not None]
            jitter = [g + rng.uniform(-0.18, 0.18) for _ in vals]
            ax.scatter(jitter, vals, s=8, alpha=0.45, color=COLORS[s], edgecolors="none")
            ax.plot([g - 0.25, g + 0.25], [sorted(vals)[len(vals) // 2]] * 2, color="#0b0b0b", lw=2)
        ax.axhline(50, color="#a3a29c", lw=1, ls=":")
        ax.set_xticks([0, 1], ["SUPPORT", "CONTRADICT"])
        ax.set_title(labels[s], fontsize=8)
    axes[0].set_ylabel("predicted accuracy_pct (black = median)")
    fig.tight_layout()
    fig.savefig(FIG / "fig2_scores_by_gold_label.png", dpi=200)
    fig.savefig(FIG / "fig2_scores_by_gold_label.pdf")


if __name__ == "__main__":
    main()
