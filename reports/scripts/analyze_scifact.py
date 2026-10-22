"""Analysis of the SciFact experiments and the paper figures.

Usage: uv run --group paper python reports/scripts/analyze_scifact.py
Reads the cached per-item records written by `afc bench` and computes, for every system, the pre-registered metrics
(docs/benchmark.md) and, for every listed pair, the paired comparison on the items both systems completed:
  pre-registered:  A vs B (primary, Exp01), A vs C and C vs B (Exp02)
  post hoc:        A vs D, D vs B (2x2 prompt x search, Exp03); A/B/C vs E (Codex agent subset, Exp04);
                   A/B/C/E vs F (Claude Code agent subset, Exp05)
plus the baseline test-retest agreement and two sensitivity analyses of the pre-registered comparisons (dropping
parse failures; dropping leak-flagged items). Writes reports/results/scifact_analysis.json and reports/figures/.
"""

import json
import random
from statistics import median
from pathlib import Path

from auto_fact_checker.bench import metrics

R = Path(__file__).resolve().parents[1] / "results"
FIG = Path(__file__).resolve().parents[1] / "figures"
SYSTEMS = {"A_baseline": R / "exp01" / "baseline.jsonl", "B_full": R / "exp01" / "full_single_openai.jsonl",
           "C_baseline_search": R / "exp02" / "baseline_search.jsonl",
           "D_full_no_search": R / "exp03_full_no_search" / "full_no_search.jsonl",
           "E_codex_agent": R / "exp04_codex_agent" / "full_agent_codex.jsonl",
           "F_claude_agent": R / "exp05_claude_agent" / "full_agent_claude.jsonl",
           "A_retest": R / "exp01_retest" / "baseline_retest.jsonl"}
LABELS = {"A_baseline": "A: simple call", "B_full": "B: full prompt + search", "C_baseline_search": "C: simple + search",
          "D_full_no_search": "D: full prompt, no search", "E_codex_agent": "E: Codex agent, full prompt",
          "F_claude_agent": "F: Claude Code (Haiku), full prompt"}
COLORS = {"A_baseline": "#2a78d6", "B_full": "#eb6834", "C_baseline_search": "#1baf7a",
          "D_full_no_search": "#eda100", "E_codex_agent": "#e87ba4",
          "F_claude_agent": "#008300"}  # dataviz reference slots 1-6, fixed order
PAIRS = [("A_baseline", "B_full", "pre-registered primary"), ("A_baseline", "C_baseline_search", "pre-registered"),
         ("C_baseline_search", "B_full", "pre-registered"), ("A_baseline", "D_full_no_search", "post hoc"),
         ("D_full_no_search", "B_full", "post hoc"), ("A_baseline", "E_codex_agent", "post hoc"),
         ("B_full", "E_codex_agent", "post hoc"), ("C_baseline_search", "E_codex_agent", "post hoc"),
         ("A_baseline", "F_claude_agent", "post hoc"), ("B_full", "F_claude_agent", "post hoc"),
         ("C_baseline_search", "F_claude_agent", "post hoc"), ("E_codex_agent", "F_claude_agent", "post hoc")]


def load(path: Path) -> dict:
    return {r["id"]: r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines())} if path.exists() else {}


def recalls(y, p) -> dict:
    pred = metrics.predictions(y, p)
    return {name: (sum(pred[i] == cls for i, t in enumerate(y) if t == cls) / max(sum(t == cls for t in y), 1))
            for cls, name in ((True, "SUPPORT_recall"), (False, "CONTRADICT_recall"))}


def compare(recs, a, b, keep=None) -> dict:
    """Paired comparison b - a on the items both systems completed (optionally filtered by `keep`)."""
    ids = sorted(set(recs[a]) & set(recs[b]))
    ids = [i for i in ids if keep is None or keep(i)]
    y = [recs[a][i]["label"] for i in ids]
    pa, pb = [recs[a][i]["p_true"] for i in ids], [recs[b][i]["p_true"] for i in ids]
    ca = [x == t for x, t in zip(metrics.predictions(y, pa), y)]
    cb = [x == t for x, t in zip(metrics.predictions(y, pb), y)]
    d, lo, hi = metrics.paired_bootstrap(y, pa, pb, metrics.balanced_accuracy, n_boot=10_000, seed=0)
    da, alo, ahi = metrics.paired_bootstrap(y, pa, pb, metrics.auroc, n_boot=2_000, seed=0)  # secondary metric
    return {"n": len(ids), "delta_balanced_accuracy": d, "ci95": [lo, hi], "mcnemar": metrics.mcnemar_exact(ca, cb),
            "delta_auroc": da, "auroc_ci95": [alo, ahi]}


def main() -> None:
    recs = {k: load(v) for k, v in SYSTEMS.items()}
    out = {"systems": {}, "comparisons": {}, "sensitivity": {}}
    for s in LABELS:
        if not recs[s]:
            continue
        ids = sorted(recs[s])
        y, p = [recs[s][i]["label"] for i in ids], [recs[s][i]["p_true"] for i in ids]
        out["systems"][s] = metrics.binary_metrics(y, p) | recalls(y, p) | {
            "cost_usd": sum(recs[s][i]["cost_usd"] for i in ids),
            "mean_searches": sum(recs[s][i]["searches"] for i in ids) / len(ids),
            "leak_items": sum(recs[s][i]["leak"] for i in ids)}
    for a, b, kind in PAIRS:
        if recs[a] and recs[b]:
            out["comparisons"][f"{b}_minus_{a}"] = compare(recs, a, b) | {"kind": kind}
    pre = [(a, b) for a, b, kind in PAIRS if kind.startswith("pre") and recs[a] and recs[b]]
    # Sensitivity filters use only the two systems of each pair (an item is never dropped because a third failed).
    for name, keep in (("parse_ok_only", lambda a, b: lambda i: all(recs[s][i]["p_true"] is not None for s in (a, b))),
                       ("no_leak_flag", lambda a, b: lambda i: not any(recs[s][i]["leak"] for s in (a, b)))):
        out["sensitivity"][name] = {f"{b}_minus_{a}": compare(recs, a, b, keep(a, b)) for a, b in pre}
    if recs["A_retest"]:
        both = sorted(set(recs["A_baseline"]) & set(recs["A_retest"]))
        y = [recs["A_baseline"][i]["label"] for i in both]
        p1 = metrics.predictions(y, [recs["A_baseline"][i]["p_true"] for i in both])
        p2 = metrics.predictions(y, [recs["A_retest"][i]["p_true"] for i in both])
        out["test_retest"] = {"n": len(both), "prediction_agreement": sum(x == z for x, z in zip(p1, p2)) / len(both),
                              "retest_balanced_accuracy": metrics.balanced_accuracy(
                                  y, [recs["A_retest"][i]["p_true"] for i in both]),
                              "retest_minus_original": compare(recs, "A_baseline", "A_retest")}
    (R / "scifact_analysis.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    figures(recs, out)


def figures(recs, out) -> None:
    """Fig 1: balanced accuracy per system with a 95% percentile bootstrap CI over items (each system on its own
    items; n shown). Fig 2: distribution of the predicted accuracy_pct by gold label for the 200-item systems."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(exist_ok=True)
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    rng = random.Random(0)
    names = [s for s in LABELS if s in out["systems"]]
    fig, ax = plt.subplots(figsize=(6.2, 0.55 * len(names) + 0.8))
    for k, s in enumerate(names):
        ids = sorted(recs[s])
        y, p = [recs[s][i]["label"] for i in ids], [recs[s][i]["p_true"] for i in ids]
        boots = sorted(metrics.balanced_accuracy(*zip(*[(y[i], p[i]) for i in (rng.randrange(len(y)) for _ in y)]))
                       for _ in range(5000))
        est, lo, hi = out["systems"][s]["balanced_accuracy"], boots[125], boots[4874]
        ax.plot([lo, hi], [k, k], color=COLORS[s], lw=2, solid_capstyle="round")
        ax.plot([est], [k], "o", color=COLORS[s], ms=8, mec="white", mew=2)
        ax.text(1.01, k, f"{est:.3f} [{lo:.3f}, {hi:.3f}]  n={len(ids)}", va="center", fontsize=8, color="#52514e",
                transform=ax.get_yaxis_transform(), clip_on=False)
    ax.axvline(0.5, color="#a3a29c", lw=1, ls=":")
    ax.set_yticks(range(len(names)), [LABELS[s] for s in names])
    ax.set_xlim(0.45, 1.0)
    ax.set_xlabel("balanced accuracy with 95% bootstrap CI (dotted line = chance)")
    ax.invert_yaxis()
    fig.savefig(FIG / "fig1_balanced_accuracy.png", dpi=200, bbox_inches="tight")
    fig.savefig(FIG / "fig1_balanced_accuracy.pdf", bbox_inches="tight")

    full = [s for s in names if len(recs[s]) >= 200]
    fig, axes = plt.subplots(1, len(full), figsize=(1.9 * len(full) + 0.6, 2.4), sharey=True, squeeze=False)
    axes = axes[0]
    for ax, s in zip(axes, full):
        ids = sorted(recs[s])
        for g, gold in enumerate((True, False)):
            vals = [100 * recs[s][i]["p_true"] for i in ids if recs[s][i]["label"] == gold
                    and recs[s][i]["p_true"] is not None]
            ax.scatter([g + rng.uniform(-0.18, 0.18) for _ in vals], vals, s=7, alpha=0.45, color=COLORS[s],
                       edgecolors="none")
            if vals:
                # Average the middle pair for even samples: https://docs.python.org/3/library/statistics.html#statistics.median
                ax.plot([g - 0.25, g + 0.25], [median(vals)] * 2, color="#0b0b0b", lw=2)
        ax.axhline(50, color="#a3a29c", lw=1, ls=":")
        ax.set_xticks([0, 1], ["SUPPORT", "CONTRA."])
        ax.set_title(LABELS[s], fontsize=8)
    axes[0].set_ylabel("model-reported accuracy (%)")
    fig.suptitle("Black bar = median; dotted line = decision threshold (50%)", fontsize=8, y=1.02)
    fig.savefig(FIG / "fig2_scores_by_gold_label.png", dpi=200, bbox_inches="tight")
    fig.savefig(FIG / "fig2_scores_by_gold_label.pdf", bbox_inches="tight")


if __name__ == "__main__":
    main()
