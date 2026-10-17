"""Exp08: error-injection benchmark on AI-research text; one vs several correction passes, naive vs rigorous prompt.

Local:
- `build` fetches Wikipedia leads and arXiv abstracts (bench/sources.py), draws a seeded number of errors k (0-5)
  per passage, asks one LLM call to inject exactly k objectively checkable factual errors (prompts/bench/
  inject_errors.md), validates every edit in code and writes the frozen dataset (JSONL).
- `ai_error_item` runs a forced-pass correction loop on the corrupted passage, records the text after every pass and
  lets independent reference judges (bench/judge.py:judge_reference) score each distinct text against the original.
Global context: `afc ai-errors build|run`; records are cached per passage by bench/run.py:run_system (resumable,
cost capped, failed items retried) and analysed by reports/scripts/analyze_ai_errors.py. Design and hypotheses are
pre-registered in docs/ai_error_bench.md. Error injection follows the synthetic-perturbation idea of FactCC
(Kryscinski et al. 2020, https://arxiv.org/abs/1910.12840).
"""

import argparse
import difflib
import json
import logging
import random
from functools import partial
from pathlib import Path

from ..config import FactCheckConfig, load_preset
from ..pipeline import run_fact_check
from ..results import RUNS
from ..schema import InjectionList
from ..spend import BudgetExceeded
from . import sources
from .correction import passes
from .datasets import BenchItem
from .judge import judge_reference, llm_json
from .run import _sources, run_system

LOG = logging.getLogger("afc.bench.ai_errors")
WIKIPEDIA = ["AlexNet", "Transformer (deep learning architecture)", "Generative adversarial network",
             "BERT (language model)", "GPT-3", "Reinforcement learning from human feedback", "AlphaGo",
             "Diffusion model", "Long short-term memory", "Residual neural network"]
ARXIV = ["1706.03762", "2106.09685", "2005.14165", "2001.08361", "2203.15556", "2205.14135", "1810.04805",
         "1512.03385", "2006.11239", "2203.02155"]
KS = [0, 0, 1, 2, 2, 3, 3, 4, 4, 5]  # errors per passage, shuffled (seeded) within each source: 24 per source
TYPES = ["wrong number or year", "wrong person or organisation", "swapped entity (wrong model, dataset or method)",
         "negation or reversed direction", "absurd overclaim"]
PASSES = 4  # forced passes per passage (accuracy_threshold 101 in the configs, so the loop never self-stops)
SELF_STOP = 90  # derived self-stop: the first pass whose every claim is self-rated >= 90% (the UI default)


def validate(text: str, errors: list, k: int) -> list[dict]:
    """The first k usable edits: exact sentence of the passage, one edit per sentence, a real but small change."""
    out, used = [], set()
    for e in errors:
        o, p = e.original_sentence.strip(), e.perturbed_sentence.strip()
        if (o and o in text and o not in used and p and p != o and p not in text
                and difflib.SequenceMatcher(None, o, p).ratio() >= 0.5 and e.false_fact and e.true_fact):
            used.add(o)
            out.append({"id": len(out) + 1, **e.model_dump(), "original_sentence": o, "perturbed_sentence": p})
        if len(out) == k:
            break
    return out


def perturb(text: str, errors: list[dict]) -> str:
    for e in errors:
        text = text.replace(e["original_sentence"], e["perturbed_sentence"], 1)
    return text


def inject(text: str, k: int, cfg: FactCheckConfig, label: str, attempts: int = 3) -> tuple[list[dict], list[str]]:
    """Ask for exactly k errors (retry while fewer than k validate); returns (errors, run ids)."""
    if k == 0:
        return [], []
    run_ids = []
    for a in range(attempts):
        v, _res, run_id = llm_json("bench/inject_errors.md", {"text": text, "k": k, "types": TYPES}, InjectionList,
                                   cfg, f"{label}/a{a}")
        run_ids.append(run_id)
        errors = validate(text, v.errors if v else [], k)
        if len(errors) == k:
            return errors, run_ids
        LOG.warning("%s attempt %d: %d of %d edits valid", label, a, len(errors), k)
    raise RuntimeError(f"{label}: could not inject {k} valid errors in {attempts} attempts")


def build(out: Path, cfg: FactCheckConfig, seed: int = 0, max_words: int = 180) -> list[dict]:
    """Fetch the passages, inject the seeded number of errors and write out/dataset.jsonl."""
    rng = random.Random(seed)
    docs = [sources.fetch_wikipedia_lead(t) for t in WIKIPEDIA] + [sources.fetch_arxiv_abstract(a) for a in ARXIV]
    ks = rng.sample(KS, len(KS)) + rng.sample(KS, len(KS))  # same k distribution within each source
    rows = []
    for doc, k in zip(docs, ks):
        text = sources.trim_sentences(doc["text"], max_words)
        rid = f"{doc['source']}-{doc['url'].rstrip('/').rsplit('/', 1)[-1].lower()}"
        errors, run_ids = inject(text, k, cfg, f"inject/{rid}")
        rows.append({"id": rid, **{f: doc[f] for f in ("source", "title", "url", "license")}, "k": k,
                     "original": text, "perturbed": perturb(text, errors), "errors": errors,
                     "injector_run_ids": run_ids})
        LOG.info("[build] %s k=%d words=%d", rid, k, len(text.split()))
    out.mkdir(parents=True, exist_ok=True)
    (out / "dataset.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                       encoding="utf-8", newline="\n")
    return rows


def load(path: Path) -> list[BenchItem]:
    """Dataset rows as bench items: text = the corrupted passage, label = k (number of injected errors)."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [BenchItem(id=r["id"], text=r["perturbed"], label=r["k"], meta=r) for r in rows]


def states(ps: list[dict], perturbed: str) -> list[str]:
    """Text after pass 0 (the corrupted input) .. PASSES; a pass without a correction leaves the text unchanged and a
    loop that stopped early carries its last text forward."""
    out = [perturbed] + [p["corrected_text"] or p["input_text"] for p in ps]
    return (out + [out[-1]] * PASSES)[: PASSES + 1]


def ai_error_item(item: BenchItem, loop_cfg: FactCheckConfig, judges: dict[str, FactCheckConfig]) -> dict:
    """Run the forced-pass loop on one corrupted passage and judge the original plus every distinct state."""
    d = item.meta
    run = run_fact_check(item.text, loop_cfg)
    RUNS.pop(run.run_id, None)  # persisted in runs/<id>/run.json
    ps = passes(run, SELF_STOP)
    st = states(ps, item.text)
    stop = next((p["index"] for p in ps if p["all_accurate"]), None)  # the loop would label its input correct
    texts = list(dict.fromkeys([d["original"]] + st))
    errs = [{f: e[f] for f in ("id", "false_fact", "true_fact", "perturbed_sentence")} for e in d["errors"]]
    judged = [{name: judge_reference(t, d["original"], errs, cfg, f"judge/{name}/{item.id}/t{i}")
               for name, cfg in judges.items()} for i, t in enumerate(texts)]
    judge_cost = sum(j["cost_usd"] or 0 for js in judged for j in js.values())
    urls = _sources(run)
    first = ps[0]["self_accuracy"] if ps else None
    return {"id": item.id, "k": item.label, "label": item.label, "source": d["source"], "status": run.status,
            "stop_reason": run.stop_reason, "n_passes": len(ps), "passes": ps, "texts": texts,
            "state_text": [texts.index(t) for t in st], "self_stop_pass": stop,
            "self_stop_state": stop - 1 if stop else PASSES, "judged": judged,
            "p_true": None if first is None else first / 100, "cost_usd": run.total_cost_usd + judge_cost,
            "billed_usd": run.billed_cost_usd + judge_cost, "searches": sum(c.web_searches for c in run.calls),
            "run_id": run.run_id, "sources": urls, "found_source": d["url"] in urls,
            "errors": [c.error for c in run.calls if c.error] + [j["error"] for js in judged for j in js.values()
                                                                 if j["error"] and "refus" not in j["error"]]}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="afc ai-errors")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="fetch passages, inject errors, write DIR/dataset.jsonl")
    b.add_argument("--out", default="benchmarks/ai_errors_v1")
    b.add_argument("--injector", default="configs/bench/judge_luna.json", help="config of the injecting call")
    b.add_argument("--seed", type=int, default=0)
    r = sub.add_parser("run", help="correct every passage with one system and judge every pass")
    r.add_argument("--dataset", default="benchmarks/ai_errors_v1/dataset.jsonl")
    r.add_argument("--limit", type=int, help="use only the first K passages")
    r.add_argument("--system", required=True, help="loop configuration (preset JSON)")
    r.add_argument("--judges", nargs="+", required=True, help="judge configurations (preset JSON)")
    r.add_argument("--out", required=True)
    r.add_argument("--max-cost", type=float, required=True, help="USD cap (billed + notional) for this invocation")
    r.add_argument("--workers", type=int, default=3)
    args = ap.parse_args(argv)
    if args.cmd == "build":
        build(Path(args.out), load_preset(args.injector), args.seed)
        return 0
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    items = load(Path(args.dataset))[: args.limit]
    judges = {Path(j).stem.removeprefix("judge_"): load_preset(j) for j in args.judges}
    name = Path(args.system).stem
    try:
        run_system(name, load_preset(args.system), items, out, args.max_cost, [0.0], args.workers, LOG.info,
                   item_fn=partial(ai_error_item, judges=judges))
    except BudgetExceeded as e:
        LOG.warning("Global spend cap reached: %s", e)
    LOG.info("Done: %s", out / f"{name}.jsonl")
    return 0
