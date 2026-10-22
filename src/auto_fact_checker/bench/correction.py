"""Exp07 runner: does the iterate-until-accurate correction loop produce text that is actually correct?

Local: for every SciFact claim, run the configured loop (e.g. a Codex agent with web search, up to 20 passes,
self-stop when it rates every claim >= the threshold), record each pass, then let one or more independent judges
compare the original claim and every distinct text the loop produced with the gold abstract (bench/judge.py).
Global context: `afc correct-eval ...`; records are cached per item by bench/run.py:run_system (resumable, cost
capped, failed items retried) and analysed by reports/scripts/analyze_correction.py. Design and hypotheses are
pre-registered in docs/correction_eval.md.
"""

import argparse
import json
import logging
from functools import partial
from pathlib import Path

from ..config import FactCheckConfig, load_preset
from ..pipeline import run_fact_check
from ..results import RUNS, FactCheckRun
from ..spend import BudgetExceeded
from .datasets import load_scifact
from .judge import judge
from .run import LEAK_MARKERS, _sources, run_system

LOG = logging.getLogger("afc.bench.correction")


def passes(run: FactCheckRun, threshold: float) -> list[dict]:
    """Per pass: the text checked, the self-assessed accuracy, whether it self-labelled everything accurate, and
    the corrected text it proposed."""
    out = []
    for it in run.iterations:
        s = it.final.summary if it.final else None
        out.append({"index": it.index, "input_text": it.input_text, "self_accuracy": s.accuracy() if s else None,
                    "all_accurate": bool(s and s.all_accurate(threshold)),
                    "corrected_text": ((s.corrected_text or "").strip() or None) if s else None})
    return out


def output_text(run: FactCheckRun) -> tuple[str, bool]:
    """The loop's answer: when it self-stopped because every claim was rated accurate, the text it rated (input of
    the last pass) is what it labels correct; otherwise its latest corrected text (not self-labelled)."""
    # Older stored runs used the unqualified prefix; keep their output-selection semantics unchanged.
    if run.iterations and (run.stop_reason or "").startswith(("all claims", "model rates all returned claims")):
        return run.iterations[-1].input_text, True
    return run.current_text, False


def correction_item(item, loop_cfg: FactCheckConfig, judges: dict[str, FactCheckConfig]) -> dict:
    """Run the loop on one claim and judge the original plus every distinct produced text with every judge."""
    run = run_fact_check(item.text, loop_cfg)
    RUNS.pop(run.run_id, None)  # persisted in runs/<id>/run.json
    ps = passes(run, loop_cfg.accuracy_threshold)
    out, self_labeled = output_text(run)
    texts = list(dict.fromkeys([item.text] + [p["corrected_text"] for p in ps if p["corrected_text"]] + [out]))
    evidence = item.meta.get("evidence", [])
    judged = [{"text": t, "judges": {name: judge(t, item.text, evidence, cfg, f"judge/{name}/{item.id}/t{k}")
                                     for name, cfg in judges.items()}} for k, t in enumerate(texts)]
    judge_cost = sum(j["cost_usd"] or 0 for jt in judged for j in jt["judges"].values())
    loop_errors = [c.error for c in run.calls if c.error]
    judge_errors = [j["error"] for jt in judged for j in jt["judges"].values()
                    if j["error"] and "refus" not in j["error"]]  # refusals are outcomes, other errors are retried
    urls = _sources(run)
    first = ps[0]["self_accuracy"] if ps else None
    return {"id": item.id, "label": item.label, "status": run.status, "stop_reason": run.stop_reason,
            "n_passes": len(run.iterations), "self_labeled_correct": self_labeled, "output_text": out,
            "passes": ps, "judged": judged, "p_true": None if first is None else first / 100,
            "cost_usd": run.total_cost_usd + judge_cost, "billed_usd": run.billed_cost_usd + judge_cost,
            "searches": sum(c.web_searches for c in run.calls), "run_id": run.run_id, "sources": urls,
            "leak": any(m in u.lower() for u in urls for m in LEAK_MARKERS), "errors": loop_errors + judge_errors}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="afc correct-eval")
    ap.add_argument("--splits", nargs="+", default=["validation", "train"])
    ap.add_argument("--items-from", required=True, help="items.json of an earlier benchmark (keeps the same claims)")
    ap.add_argument("--limit", type=int, help="use only the first K items")
    ap.add_argument("--system", required=True, help="loop configuration (preset JSON)")
    ap.add_argument("--judges", nargs="+", required=True, help="judge configurations (preset JSON)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-cost", type=float, required=True, help="USD cap (billed + notional) for this invocation")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    wanted = [i["id"] for i in json.loads(Path(args.items_from).read_text(encoding="utf-8"))][: args.limit]
    pool = {i.id: i for i in load_scifact(tuple(args.splits), with_evidence=True)}
    items = [pool[i] for i in wanted if i in pool]
    (out / "items.json").write_text(json.dumps([vars(i) for i in items], indent=1, ensure_ascii=False),
                                    encoding="utf-8")
    judges = {Path(j).stem.removeprefix("judge_"): load_preset(j) for j in args.judges}
    name = Path(args.system).stem
    try:
        run_system(name, load_preset(args.system), items, out, args.max_cost, [0.0], args.workers, LOG.info,
                   item_fn=partial(correction_item, judges=judges))
    except BudgetExceeded as e:
        LOG.warning("Global spend cap reached: %s", e)
    LOG.info("Done: %s", out / f"{name}.jsonl")
    return 0
