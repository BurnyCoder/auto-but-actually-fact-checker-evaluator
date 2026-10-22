"""Benchmark runner: `afc bench --dataset scifact --systems A.json B.json --n N --max-cost USD --out DIR`.

Local: samples a seeded balanced item set, fact-checks every item with every system (a system = a preset /
FactCheckConfig JSON), caches one JSON line per (system, item) so runs resume without paying twice, stops when the
benchmark's own cost cap or the global spend cap is reached, then writes summary.json and results.md with per-system
metrics and paired comparisons of the first system (baseline) against each other system.
Global context: each item goes through pipeline.run_fact_check exactly like a UI run; the prediction is
p_true = overall_accuracy_pct / 100, or the mean claim accuracy when the overall score is missing
(schema.FactCheckSummary.accuracy); SUPPORT iff p_true >= 0.5, fixed in advance.
"""

import argparse
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..config import get_settings, load_preset
from ..pipeline import run_fact_check
from ..results import RUNS
from ..spend import BudgetExceeded
from . import metrics
from .datasets import DATASETS, sample_balanced

LEAK_MARKERS = ("scifact", "huggingface.co", "github.com", "githubusercontent.com", "allenai.org", "kaggle.com",
                "paperswithcode.com")  # the blocked benchmark hosts plus the dataset name
_WRITE = threading.Lock()
LOG = logging.getLogger("afc.bench")


def run_item(item, cfg) -> dict:
    """Fact-check one item; return the cached record (prediction, cost, sources, leakage flag)."""
    run = run_fact_check(item.text, cfg)
    RUNS.pop(run.run_id, None)  # persisted in runs/<id>/run.json; keep memory flat over hundreds of items
    final = run.iterations[-1].final if run.iterations else None
    summary = final.summary if final else None
    acc = summary.accuracy() if summary else None
    urls = _sources(run)
    return {"id": item.id, "label": item.label, "p_true": None if acc is None else acc / 100,
            "parse_ok": summary is not None, "cost_usd": run.total_cost_usd,
            "searches": sum(c.web_searches for c in run.calls), "status": run.status, "stop_reason": run.stop_reason,
            "run_id": run.run_id, "sources": urls, "leak": any(m in u.lower() for u in urls for m in LEAK_MARKERS),
            "errors": [c.error for c in run.calls if c.error]}


def _sources(run) -> list[str]:
    """Source URLs of every call of a run, read back from the per-call result files."""
    urls = []
    for f in sorted((get_settings().runs_dir / run.run_id / "calls").glob("*.result.json")):
        urls += json.loads(f.read_text(encoding="utf-8")).get("sources", [])
    return list(dict.fromkeys(urls))


def run_system(name: str, cfg, items, out: Path, max_cost: float, spent: list, workers: int, log,
               item_fn=None) -> None:
    """Run all uncached items of one system in parallel until the benchmark cost cap is hit.

    item_fn(item, cfg) -> record (default run_item); bench/correction.py and bench/ai_errors.py pass their
    loop-and-judge functions.
    """
    item_fn = item_fn or run_item
    path = out / f"{name}.jsonl"
    done = {json.loads(line)["id"] for line in path.read_text(encoding="utf-8").splitlines()} if path.exists() else set()
    todo = [i for i in items if i.id not in done]
    log(f"[{name}] {len(done)} cached, {len(todo)} to run")

    stop = threading.Event()  # set once the global spend cap is hit, so queued items are skipped

    def work(item):
        with _WRITE:
            if stop.is_set() or spent[0] >= max_cost:
                return
        rec = item_fn(item, cfg)
        with _WRITE:
            spent[0] += rec["cost_usd"]
            refused = any("refusal" in (e or "") for e in rec["errors"])  # deterministic: scored wrong, not retried
            complete = rec["status"] == "done" and (not rec["errors"] or refused)
            if complete:  # finished items (incl. refusals) are cached; transient failures are retried on resume
                with path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log(f"[{name}] {item.id} gold={item.label} p_true={rec['p_true']} cost=${rec['cost_usd']:.4f} "
            f"total=${spent[0]:.4f} leak={rec.get('leak')}" + ("" if complete else
                                                         f" NOT CACHED ({rec['status']}: {rec['stop_reason']}; "
                                                         f"errors={rec['errors']})"))
        if rec["status"] == "stopped" and "Spend cap" in (rec["stop_reason"] or ""):
            stop.set()
            raise BudgetExceeded(rec["stop_reason"])

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, todo))


def load_records(path: Path, ids: list[str]) -> dict:
    """Cached records of a system restricted to the sampled ids."""
    if not path.exists():
        return {}
    recs = {r["id"]: r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines())}
    return {i: recs[i] for i in ids if i in recs}


def summarize(names: list[str], items, out: Path) -> dict:
    """Metrics per system on the items every system completed, plus paired comparisons vs the first system."""
    ids = [i.id for i in items]
    recs = {n: load_records(out / f"{n}.jsonl", ids) for n in names}
    common = [i for i in ids if all(i in recs[n] for n in names)]
    y = [recs[names[0]][i]["label"] for i in common]
    p = {n: [recs[n][i]["p_true"] for i in common] for n in names}
    summary = {"n_common": len(common), "systems": {}, "comparisons": {}}
    for n in names:
        m = metrics.binary_metrics(y, p[n])
        m["cost_usd"] = sum(recs[n][i]["cost_usd"] for i in common)
        m["leak_items"] = sum(recs[n][i]["leak"] for i in common)
        m["mean_searches"] = sum(recs[n][i]["searches"] for i in common) / max(len(common), 1)
        summary["systems"][n] = m
    base = names[0]
    for n in (names[1:] if len(common) >= 2 else []):
        correct = {k: [pr == yy for pr, yy in zip(metrics.predictions(y, p[k]), y)] for k in (base, n)}
        d, lo, hi = metrics.paired_bootstrap(y, p[base], p[n], metrics.balanced_accuracy)
        summary["comparisons"][f"{base}_vs_{n}"] = {"delta_balanced_accuracy": d, "ci95": [lo, hi],
                                                    "mcnemar": metrics.mcnemar_exact(correct[base], correct[n])}
    return summary


def _fmt(v) -> str:
    """Three decimals, or n/a for metrics that are undefined on the available items."""
    return "n/a" if v is None else f"{v:.3f}"


def results_markdown(summary: dict) -> str:
    """Human-readable tables of summary.json for reports."""
    rows = ["| system | n | accuracy [95% Wilson CI] | balanced acc. | macro-F1 | AUROC | Brier | parse fails |"
            " leak items | mean searches | cost $ |", "|" + "---|" * 11]
    for n, m in summary["systems"].items():
        lo, hi = m["accuracy_ci"]
        rows.append(f"| {n} | {m['n']} | {m['accuracy']:.3f} [{lo:.3f}, {hi:.3f}] | {m['balanced_accuracy']:.3f} | "
                    f"{m['macro_f1']:.3f} | {_fmt(m['auroc'])} | {_fmt(m['brier'])} | {m['parse_fail']} | "
                    f"{m['leak_items']} | {m['mean_searches']:.2f} | {m['cost_usd']:.4f} |")
    rows += ["", "| comparison | Δ balanced accuracy [95% paired bootstrap CI] | McNemar b / c | exact p |",
             "|---|---|---|---|"]
    for k, c in summary["comparisons"].items():
        rows.append(f"| {k} | {c['delta_balanced_accuracy']:+.3f} [{c['ci95'][0]:+.3f}, {c['ci95'][1]:+.3f}] | "
                    f"{c['mcnemar']['b']} / {c['mcnemar']['c']} | {c['mcnemar']['pvalue']:.4f} |")
    return "\n".join(rows) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="afc bench")
    ap.add_argument("--dataset", default="scifact", choices=sorted(DATASETS))
    ap.add_argument("--splits", nargs="+", default=["validation", "train"])
    ap.add_argument("--systems", nargs="+", required=True, help="preset JSON files; the first is the baseline")
    ap.add_argument("--n", type=int, required=True, help="balanced sample size")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--exclude-from", nargs="*", default=[], help="result dirs whose item ids are excluded (pilots)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-cost", type=float, required=True, help="USD cap for this benchmark invocation")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, help="use only the first K sampled items (subset of the same sample)")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    exclude = {json.loads(line)["id"] for d in args.exclude_from for f in Path(d).glob("*.jsonl")
               for line in f.read_text(encoding="utf-8").splitlines()}
    items = sample_balanced(DATASETS[args.dataset](tuple(args.splits)), args.n, args.seed, exclude)[: args.limit]
    (out / "items.json").write_text(json.dumps([vars(i) for i in items], indent=1, ensure_ascii=False),
                                    encoding="utf-8")
    names = [Path(s).stem for s in args.systems]
    spent = [0.0]
    try:
        for name, path in zip(names, args.systems):
            run_system(name, load_preset(path), items, out, args.max_cost, spent, args.workers, LOG.info)
    except BudgetExceeded as e:
        LOG.warning("Global spend cap reached: %s", e)
    summary = summarize(names, items, out)
    summary |= {"dataset": args.dataset, "splits": args.splits, "seed": args.seed, "n_sampled": len(items),
                "systems_files": args.systems, "invocation_cost_usd": spent[0]}
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    (out / "results.md").write_text(results_markdown(summary), encoding="utf-8")
    LOG.info("Results\n%s", results_markdown(summary))
    return 0
