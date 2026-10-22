"""Exp08 analysis: judge validity, H1-H3, harm on clean controls and per-pass curves of the AI-research
error-injection benchmark (pre-registered in docs/ai_error_bench.md; written before any Exp08 correction data).

Usage: uv run --group paper python reports/scripts/analyze_ai_errors.py
Reads reports/results/exp08_ai_errors/ai_{naive,rigorous}_codex.jsonl written by `afc ai-errors run`, writes
reports/results/ai_errors_analysis.json and reports/figures/fig4_ai_errors_passes.{png,pdf}.
Statistics: paired bootstrap 95% CI of a mean difference and a cluster bootstrap by passage for error-level rates
(Efron & Tibshirani 1993); Wilcoxon signed-rank with Pratt's zero handling (scipy.stats.wilcoxon,
https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.wilcoxon.html); Spearman rank correlation
(scipy.stats.spearmanr); Cohen's kappa (sklearn.metrics.cohen_kappa_score).
"""

import json
import random
import re
import statistics as st
import sys
from pathlib import Path

from scipy.stats import spearmanr, wilcoxon
from sklearn.metrics import cohen_kappa_score

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling script with the pre-registered helpers
from analyze_correction import load, wilson  # noqa: E402

R = Path(__file__).resolve().parents[1] / "results"
FIG = Path(__file__).resolve().parents[1] / "figures"
DATA = R / "exp08_ai_errors"
ARMS = {"rigorous": DATA / "ai_rigorous_codex.jsonl", "naive": DATA / "ai_naive_codex.jsonl"}
PRIMARY, SECONDARY = "haiku", "luna"  # primary judge = the other model family from the gpt-6-luna corrector
PASSES = 4
COLORS = {"rigorous": "#2a78d6", "naive": "#eb6834", "reference": "#8a8a8a"}  # dataviz reference slots 1-2 + gray
NUM = re.compile(r"\d[\d,.]*\d|\d")


def judged(rec: dict, state: int | None, judge: str) -> dict:
    """The judge's verdict on the text after `state` passes (None = the original passage)."""
    i = 0 if state is None else rec["state_text"][state]
    return rec["judged"][i].get(judge) or {}


def score(rec, state, judge=PRIMARY):
    return judged(rec, state, judge).get("overall")


def fixes(rec, state, judge=PRIMARY) -> dict:
    """{error id (str): 1 / 0.5 / 0 / None}; JSON turns the ids into strings."""
    return {str(k): v for k, v in (judged(rec, state, judge).get("fix") or {}).items()}


def introduced(rec, state, judge=PRIMARY):
    return judged(rec, state, judge).get("introduced")


def mean(xs):
    xs = [x for x in xs if x is not None]
    return st.mean(xs) if xs else None


def boot(values: list[list[float]], stat, n_boot: int = 10_000, seed: int = 0) -> list:
    """95% percentile CI of stat(resampled clusters); one cluster per passage."""
    rng, n = random.Random(seed), len(values)
    if n == 0:
        return [None, None]
    draws = sorted(s for s in (stat([values[rng.randrange(n)] for _ in range(n)]) for _ in range(n_boot))
                   if s is not None)
    return [draws[int(0.025 * len(draws))], draws[int(0.975 * len(draws)) - 1]] if draws else [None, None]


def paired(a: list, b: list) -> dict:
    """Paired comparison b - a over passages with both values: mean delta, bootstrap CI, Wilcoxon (Pratt)."""
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    d = [y - x for x, y in pairs]
    out = {"n": len(d), "mean_first": mean([x for x, _ in pairs]), "mean_second": mean([y for _, y in pairs]),
           "delta": mean(d), "ci95": boot([[v] for v in d], lambda c: mean([v[0] for v in c])),
           "better": sum(v > 0 for v in d), "worse": sum(v < 0 for v in d), "same": sum(v == 0 for v in d)}
    out["wilcoxon_p"] = float(wilcoxon(d, zero_method="pratt").pvalue) if any(d) else 1.0
    return out


def error_rate(recs, state, judge=PRIMARY, where=lambda e: True) -> dict:
    """Mean fix score (corrected 1, partially 0.5, uncorrected 0) over injected errors, cluster CI by passage."""
    clusters = [[v for e in r["meta_errors"] if where(e) and (v := fixes(r, state, judge).get(str(e["id"])))
                 is not None] for r in recs]
    clusters = [c for c in clusters if c]
    flat = lambda cs: mean([v for c in cs for v in c])  # noqa: E731
    return {"n_errors": sum(map(len, clusters)), "n_passages": len(clusters), "mean": flat(clusters),
            "ci95": boot(clusters, flat), "fully_corrected": sum(v == 1 for c in clusters for v in c)}


def numeric_rule(e: dict, text: str):
    """Deterministic status of a number/year error: 1 if the true number is back and the false one gone, 0.5 if
    only the false one is gone, 0 if the false number is still there; None if the edit has no number change."""
    o, p = set(NUM.findall(e["original_sentence"])), set(NUM.findall(e["perturbed_sentence"]))
    true, false = o - p, p - o
    if not false:
        return None
    have = set(NUM.findall(text))
    return 0.0 if false & have else 1.0 if true and true <= have else 0.5


def validity(recs) -> dict:
    out = {}
    for j in (PRIMARY, SECONDARY):
        orig = [score(r, None, j) for r in recs]
        pert = [(r["k"], score(r, 0, j)) for r in recs]
        rho = spearmanr([k for k, s in pert if s is not None], [s for _, s in pert if s is not None])
        out[j] = {"original_mean_score": mean(orig), "original_min_score": min((s for s in orig if s is not None),
                                                                               default=None),
                  "original_introduced_mean": mean([introduced(r, None, j) for r in recs]),
                  "original_fix_mean": error_rate(recs, None, j)["mean"],
                  "perturbed_fix_mean": error_rate(recs, 0, j)["mean"],
                  "perturbed_score_by_k": {k: mean([s for kk, s in pert if kk == k]) for k in range(6)},
                  "spearman_k_vs_perturbed_score": [float(rho.statistic), float(rho.pvalue)],
                  "missing_verdicts": sum(v.get("overall") is None for r in recs for t in r["judged"]
                                          for v in [t.get(j) or {}])}
    rule, jst = [], []  # deterministic number check vs primary judge on every judged state
    for r in recs:
        for s in range(PASSES + 1):
            text = r["texts"][r["state_text"][s]]
            for e in r["meta_errors"]:
                v, jv = numeric_rule(e, text), fixes(r, s, PRIMARY).get(str(e["id"]))
                if v is not None and jv is not None:
                    rule.append(v)
                    jst.append(jv)
    out["numeric_rule_vs_judge"] = {"n": len(rule), "exact_agreement": sum(a == b for a, b in zip(rule, jst)) /
                                    len(rule) if rule else None,
                                    "kappa": cohen_kappa_score([str(a) for a in rule], [str(b) for b in jst])
                                    if len(set(rule) | set(jst)) > 1 else None}
    pairs = [(t.get(PRIMARY, {}).get("overall"), t.get(SECONDARY, {}).get("overall")) for r in recs for t in r["judged"]]
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    out["judge_agreement_overall"] = {"n": len(pairs), "spearman": float(spearmanr(*zip(*pairs)).statistic)
                                      if len(pairs) > 2 else None, "mean_abs_diff": mean([abs(a - b) for a, b in pairs])}
    return out


def curve(recs, judge=PRIMARY) -> list[dict]:
    rows = []
    for s in range(PASSES + 1):
        vals = [score(r, s, judge) for r in recs]
        rows.append({"pass": s, "score_mean": mean(vals), "score_ci95": boot([[v] for v in vals if v is not None],
                                                                              lambda c: mean([v[0] for v in c])),
                     "fix": error_rate(recs, s, judge), "introduced_mean": mean([introduced(r, s, judge) for r in recs]),
                     "self_accuracy_mean": mean([r["passes"][s - 1]["self_accuracy"] for r in recs
                                                 if 0 < s <= len(r["passes"])])})
    return rows


def arm_stats(recs) -> dict:
    sc = lambda s, j=PRIMARY: [score(r, s, j) for r in recs]  # noqa: E731
    net = lambda s: [sum(v for v in fixes(r, s).values() if v is not None) - (introduced(r, s) or 0)  # noqa: E731
                     for r in recs]
    selfstop = [score(r, r["self_stop_state"]) for r in recs]
    controls = [r for r in recs if r["k"] == 0]
    out = {"n": len(recs), "curve": curve(recs), "curve_secondary": curve(recs, SECONDARY),
           "H1_pass4_vs_pass1": paired(sc(1), sc(PASSES)),
           "H1_pass4_vs_pass1_secondary": paired(sc(1, SECONDARY), sc(PASSES, SECONDARY)),
           "H3_pass1_vs_perturbed": paired(sc(0), sc(1)),
           "net_fixes_pass4_vs_pass1": paired(net(1), net(PASSES)),
           "fix_rate_pass4_vs_pass1": paired([mean(fixes(r, 1).values()) for r in recs],
                                            [mean(fixes(r, PASSES).values()) for r in recs]),
           "self_stop": {"pass_counts": {str(p): sum(r["self_stop_pass"] == p for r in recs)
                                         for p in [None, *range(1, PASSES + 1)]},
                         "vs_pass1": paired(sc(1), selfstop), "vs_pass4": paired(sc(PASSES), selfstop)},
           "controls_k0": {"n": len(controls), "score_by_pass": [mean([score(r, s) for r in controls])
                                                                 for s in range(PASSES + 1)],
                           "introduced_by_pass": [mean([introduced(r, s) for r in controls])
                                                  for s in range(PASSES + 1)],
                           "unchanged_after_pass4": sum(r["state_text"][PASSES] == r["state_text"][0]
                                                        for r in controls)},
           "by_k": {k: {"n": len(g), "score_pass1": mean([score(r, 1) for r in g]),
                        "score_pass4": mean([score(r, PASSES) for r in g]),
                        "fix_pass1": error_rate(g, 1)["mean"], "fix_pass4": error_rate(g, PASSES)["mean"]}
                    for k in range(6) if (g := [r for r in recs if r["k"] == k])},
           "by_source": {s: {"n": len(g), "score_pass1": mean([score(r, 1) for r in g]),
                             "score_pass4": mean([score(r, PASSES) for r in g])}
                         for s in ("wikipedia", "arxiv") if (g := [r for r in recs if r["source"] == s])},
           "found_original_source": sum(r["found_source"] for r in recs),
           "searches_mean": mean([r["searches"] for r in recs]),
           "cost_usd_notional_mean": mean([r["cost_usd"] for r in recs]), "billed_usd": sum(r["billed_usd"] for r in recs),
           "errors": sum(bool(r["errors"]) for r in recs)}
    types = sorted({e["error_type"] for r in recs for e in r["meta_errors"]})
    out["by_error_type"] = {t: {"pass1": error_rate(recs, 1, where=lambda e, t=t: e["error_type"] == t),
                                "pass4": error_rate(recs, PASSES, where=lambda e, t=t: e["error_type"] == t)}
                            for t in types}
    return out


def attach_errors(recs: list[dict], dataset: dict) -> list[dict]:
    """Copy the injected-error list of each passage from the frozen dataset into its record."""
    return [r | {"meta_errors": dataset[r["id"]]["errors"]} for r in recs if r["id"] in dataset]


def analyse(arms: dict[str, list[dict]]) -> dict:
    res = {"primary_judge": PRIMARY, "secondary_judge": SECONDARY, "arms": {a: arm_stats(r) for a, r in arms.items()
                                                                           if r}}
    res["validity"] = validity([r for recs in arms.values() for r in recs])
    if all(arms.get(a) for a in ("naive", "rigorous")):
        nv, rg = ({r["id"]: r for r in arms[a]} for a in ("naive", "rigorous"))
        ids = sorted(set(nv) & set(rg))
        res["H2_rigorous_vs_naive_pass1"] = paired([score(nv[i], 1) for i in ids], [score(rg[i], 1) for i in ids])
        res["H2_rigorous_vs_naive_pass4"] = paired([score(nv[i], PASSES) for i in ids],
                                                   [score(rg[i], PASSES) for i in ids])
        res["retest_perturbed_same_text"] = {j: {"mean_abs_diff": mean([abs(score(nv[i], 0, j) - score(rg[i], 0, j))
                                                                        for i in ids if score(nv[i], 0, j) is not None
                                                                        and score(rg[i], 0, j) is not None])}
                                             for j in (PRIMARY, SECONDARY)}
    return res


def figure(res: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    arms = [a for a in ("rigorous", "naive") if a in res["arms"]]
    if not arms:
        return
    FIG.mkdir(exist_ok=True)
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.4, 3.0))
    xs = list(range(PASSES + 1))
    for a in arms:
        c = res["arms"][a]["curve"]
        for ax, get, ci in ((ax1, lambda r: r["score_mean"], lambda r: r["score_ci95"]),
                            (ax2, lambda r: r["fix"]["mean"], lambda r: r["fix"]["ci95"])):
            ax.plot(xs, [get(r) for r in c], "-o", color=COLORS[a], lw=1.5, ms=6,
                    label=f"{a} prompt (n = {res['arms'][a]['n']})")
            ax.fill_between(xs, [ci(r)[0] for r in c], [ci(r)[1] for r in c], color=COLORS[a], alpha=0.15, lw=0)
    ref = res["validity"][PRIMARY]["original_mean_score"]
    ax1.axhline(ref, ls="--", lw=1, color=COLORS["reference"], label="original reference passage")
    ax1.set_ylim(0, 102)
    ax1.set_ylabel(f"factual accuracy score, 0-100 ({PRIMARY} judge)")
    ax2.set_ylim(0, 1.02)
    ax2.set_ylabel("weighted edit-fix score (1 / 0.5 / 0, mean)")
    for ax in (ax1, ax2):
        ax.set_xticks(xs)
        ax.set_xlabel("correction passes (0 = corrupted input)")
        ax.grid(axis="y", lw=0.4, alpha=0.4)
    ax1.legend(fontsize=7, loc="lower right", frameon=False)
    fig.tight_layout()
    fig.savefig(FIG / "fig4_ai_errors_passes.png", dpi=200, bbox_inches="tight")
    fig.savefig(FIG / "fig4_ai_errors_passes.pdf", bbox_inches="tight")


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    dataset = {r["id"]: r for r in map(json.loads, (root / "benchmarks" / "ai_errors_v1" / "dataset.jsonl")
                                       .read_text(encoding="utf-8").splitlines())}
    res = analyse({a: attach_errors(load(p), dataset) for a, p in ARMS.items()})
    res["k0_changed_wilson"] = {a: wilson(s["controls_k0"]["n"] - s["controls_k0"]["unchanged_after_pass4"],
                                          s["controls_k0"]["n"]) for a, s in res["arms"].items()}
    (R / "ai_errors_analysis.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))
    figure(res)


if __name__ == "__main__":
    main()
