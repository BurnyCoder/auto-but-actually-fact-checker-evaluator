"""Metrics and paired statistical tests for comparing fact-checking systems on the same binary items.

Local: accuracy with Wilson CI, balanced accuracy, macro-F1, AUROC and Brier score on p_true = accuracy_pct/100,
exact McNemar test on paired correctness, paired bootstrap CI for metric differences.
Global context: bench/run.py writes these into summary.json / results.md, which the experiment reports cite.
References: Wilson CI https://www.statsmodels.org/stable/generated/statsmodels.stats.proportion.proportion_confint.html ;
McNemar (exact) https://www.statsmodels.org/stable/generated/statsmodels.stats.contingency_tables.mcnemar.html and
Dietterich 1998 (Neural Computation 10(7)); paired bootstrap: Berg-Kirkpatrick et al. 2012 (EMNLP);
sklearn metrics https://scikit-learn.org/stable/api/sklearn.metrics.html
"""

import random

from sklearn.metrics import balanced_accuracy_score, f1_score, roc_auc_score
from statsmodels.stats.contingency_tables import mcnemar
from statsmodels.stats.proportion import proportion_confint


def predictions(y_true: list[bool], p_true: list[float | None], threshold: float = 0.5) -> list[bool]:
    """Predicted labels; an unparsed answer (None) is scored as wrong (pre-registered conservative rule)."""
    return [(not y) if p is None else p >= threshold for y, p in zip(y_true, p_true)]


def balanced_accuracy(y_true, p_true) -> float:
    """Mean of per-class recalls; 0.5 = chance on a binary task whatever the class balance.

    Plain Python (same definition as sklearn.metrics.balanced_accuracy_score, checked in tests) because the
    paired bootstrap calls it 20,000 times.
    """
    pred = predictions(y_true, p_true)
    recalls = []
    for cls in (True, False):
        idx = [i for i, y in enumerate(y_true) if y == cls]
        if idx:
            recalls.append(sum(pred[i] == cls for i in idx) / len(idx))
    return sum(recalls) / len(recalls) if recalls else 0.0


def auroc(y_true, p_true) -> float:
    """Area under the ROC curve of p_true (unparsed answers scored 0.5); defined only when both classes occur."""
    return float(roc_auc_score(y_true, [0.5 if p is None else p for p in p_true])) if len(set(y_true)) == 2 else 0.5


def binary_metrics(y_true: list[bool], p_true: list[float | None], threshold: float = 0.5) -> dict:
    """All per-system metrics; probability metrics use 0.5 for unparsed answers."""
    pred = predictions(y_true, p_true, threshold)
    correct = sum(p == y for p, y in zip(pred, y_true))
    n = len(y_true)
    probs = [0.5 if p is None else p for p in p_true]
    both = len(set(y_true)) == 2
    return {"n": n, "accuracy": correct / n if n else 0.0,
            "accuracy_ci": list(proportion_confint(correct, n, alpha=0.05, method="wilson")) if n else [0, 0],
            "balanced_accuracy": float(balanced_accuracy_score(y_true, pred)) if n else 0.0,
            "macro_f1": float(f1_score(y_true, pred, average="macro")) if n else 0.0,
            "auroc": float(roc_auc_score(y_true, probs)) if both else None,
            "brier": sum((p - y) ** 2 for p, y in zip(probs, y_true)) / n if n else None,
            "parse_fail": sum(p is None for p in p_true)}


def mcnemar_exact(correct_a: list[bool], correct_b: list[bool]) -> dict:
    """Exact (binomial) McNemar test on paired correctness; b = A right/B wrong, c = A wrong/B right."""
    b = sum(a and not bb for a, bb in zip(correct_a, correct_b))
    c = sum(bb and not a for a, bb in zip(correct_a, correct_b))
    both = sum(a and bb for a, bb in zip(correct_a, correct_b))
    neither = len(correct_a) - b - c - both
    res = mcnemar([[both, b], [c, neither]], exact=True)
    return {"b": b, "c": c, "pvalue": float(res.pvalue)}


def paired_bootstrap(y_true, p_a, p_b, metric_fn, n_boot: int = 10_000, seed: int = 0) -> tuple[float, float, float]:
    """Observed metric(B) - metric(A) and its 95% percentile CI from resampling items (same indices for both)."""
    rng = random.Random(seed)
    n = len(y_true)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    delta = metric_fn(y_true, p_b) - metric_fn(y_true, p_a)
    stats = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        ys = [y_true[i] for i in idx]
        if len(set(ys)) < 2:  # balanced accuracy needs both classes in the resample
            continue
        stats.append(metric_fn(ys, [p_b[i] for i in idx]) - metric_fn(ys, [p_a[i] for i in idx]))
    if not stats:  # too few items (or a single class) to resample: no interval
        return delta, float("nan"), float("nan")
    stats.sort()
    return delta, stats[int(0.025 * len(stats))], stats[min(int(0.975 * len(stats)), len(stats) - 1)]
