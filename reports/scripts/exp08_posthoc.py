"""Exp08 post-hoc analyses (decided after seeing the pre-registered results; exploratory).

Usage: uv run python reports/scripts/exp08_posthoc.py
1. Per-error status transitions (primary judge), passage length and hedge-word counts per pass: is the rigorous
   arm's falling fix rate re-introduction of the false fact, or loss of the true fact?
2. Time, notional cost, searches and output tokens per pass, read from runs/<id>/run.json.
3. Historical AI-agent audit annotations and a separate dated, sourced reassessment of every pass-1 flag.
4. A post-hoc sensitivity excluding the ambiguous LSTM annotation, without changing frozen records or judges.
Writes reports/results/exp08_posthoc.json.
"""

import json
import statistics as st
from collections import Counter
from pathlib import Path

from auto_fact_checker.config import get_settings
from auto_fact_checker.results import FactCheckRun

R = Path(__file__).resolve().parents[1] / "results"
DATA = R / "exp08_ai_errors"
HEDGES = (" may ", " might ", " commonly ", " often ", " some ", " reported ", " described as", " typically ")
# Pass-1 introduced errors (Haiku judge) in file order: naive N01-N08, rigorous R01-R14 (listed by this script).
# Historical labels are preserved for provenance, not endorsed as verified truth. The dated reassessment below
# distinguishes source conflicts and unresolved interpretations; see claim_provenance() for item-level evidence.
AUDIT = {"false": [],
         "true_per_primary_source": ["N01", "N02", "N06", "N07", "N08", "R02", "R04", "R06", "R08", "R09", "R10",
                                     "R11", "R13"],
         "hedge_or_scope_qualification": ["N03", "N04", "N05", "R01", "R03", "R05", "R07", "R12", "R14"]}
AUDIT_SOURCES = {
    "AlexNet: 500,000 neurons on the NeurIPS abstract page vs 650,000 in the PDF; 15.3% vs 26.2% runner-up (10.9 "
    "points)": "https://papers.nips.cc/paper_files/paper/2012/hash/c399862d3b9d6b76c8436e924a68c45b-Abstract.html",
    "Transformer: Results prose 41.0 BLEU vs abstract 41.8; parsing F1 91.3 / 92.7; feed-forward sublayers; 2017":
        "https://arxiv.org/abs/1706.03762",
    "Self-attention is permutation-equivariant (Lee et al. 2019, Set Transformer)": "https://arxiv.org/abs/1810.00825",
    "Chinchilla: baselines trained on ~300B tokens; worse than Gopher on 4 MMLU and 4 BIG-bench tasks":
        "https://arxiv.org/abs/2203.15556",
    "ResNet: CIFAR-10 networks of 110 and 1202 layers (abstract rounds to 100 / 1000)": "https://arxiv.org/abs/1512.03385"}


def load(arm: str) -> list[dict]:
    return [json.loads(line) for line in (DATA / f"ai_{arm}_codex.jsonl").read_text(encoding="utf-8").splitlines()]


def text(r, s):
    return r["texts"][r["state_text"][s]]


def haiku(r, s):
    return r["judged"][r["state_text"][s]]["haiku"]


def fix_summary(values) -> dict:
    """Separate full restorations from half-credit annotations; missing values stay visible.

    This is the reference-judge scale in prompts/judge/reference_errors.md, not a percent of true statements.
    """
    present = [v for v in values if v is not None]  # A refused/missing judgment cannot be assumed wrong or right.
    full = sum(v == 1 for v in present)  # Half-credit deletions and hedges do not restore the annotated fact.
    return {"n_scored": len(present), "n_missing": len(values) - len(present),
            "weighted_mean": st.mean(present) if present else None, "fully_corrected": full,
            "fully_corrected_fraction": full / len(present) if present else None}


def lstm_sensitivity(recs) -> dict:
    """Exclude one ambiguous capability claim post hoc; retain the original candidate texts and judge outputs.

    LSTM's ability to retain information for thousands of steps does not make 'can last three' false.
    Source: https://doi.org/10.1162/neco.1997.9.8.1735 ; frozen dataset line 9, annotation 3.
    """
    excluded = {"passage": "wikipedia-long_short-term_memory", "error_id": "3"}
    return {"excluded": excluded, "note": "Post hoc, 2026-10-22; no text was changed or rejudged. Whole-text scores are unchanged.",
            **{f"pass{s}": fix_summary([v for r in recs for e, v in haiku(r, s)["fix"].items()
                                        if (r["id"], e) != (excluded["passage"], excluded["error_id"])])
               for s in (1, 4)}}


def claim_provenance() -> dict:
    """Read the dated, manually sourced reassessment; retain historical AUDIT labels separately."""
    return json.loads((R / "exp08_claim_provenance_2026-10-22.json").read_text(encoding="utf-8"))


def drift(recs) -> dict:
    out = {"status_by_pass": [dict(Counter(str(v) for r in recs for v in haiku(r, s)["fix"].values()))
                              for s in range(5)],
           "words_by_pass": [st.mean(len(text(r, s).split()) for r in recs) for s in range(5)],
           "hedge_words_by_pass": [sum(text(r, s).lower().count(h) for r in recs for h in HEDGES) for s in range(5)],
           "transitions_pass1_to_pass4": dict(Counter(f"{haiku(r, 1)['fix'].get(e)}->{haiku(r, 4)['fix'].get(e)}"
                                                      for r in recs for e in haiku(r, 1)["fix"]))}
    out["passages_rewritten_every_pass"] = sum(len(set(r["state_text"][1:])) == 4 for r in recs)
    return out


def per_pass(recs, runs_dir=None) -> dict:
    """Aggregate local call records only when all are available; a clean clone has no published raw runs."""
    runs_dir = get_settings().runs_dir if runs_dir is None else runs_dir
    missing = [r["run_id"] for r in recs if not (runs_dir / r["run_id"] / "run.json").exists()]
    if missing:  # Partial coverage would silently change the denominator of published timing/cost claims.
        return {"available": False, "missing_run_ids": missing, "values": None}
    rows = {p: {"s": [], "usd": [], "searches": [], "out_tokens": []} for p in range(1, 5)}
    for r in recs:
        run = FactCheckRun.model_validate_json((runs_dir / r["run_id"] / "run.json")
                                               .read_text(encoding="utf-8"))
        for p, v in rows.items():
            calls = [c for c in run.calls if c.label.startswith(f"iter{p}/")]
            v["s"].append(sum(c.duration_s for c in calls))
            v["usd"].append(sum(c.cost_usd or 0 for c in calls))
            v["searches"].append(sum(c.web_searches for c in calls))
            v["out_tokens"].append(sum(c.output_tokens or 0 for c in calls))
    return {p: {k: st.mean(x) for k, x in v.items()} for p, v in rows.items()}


def main() -> None:
    arms = {a: load(a) for a in ("naive", "rigorous")}
    flagged = {f"{a[0].upper()}{i:02d}": (r["id"], x) for a, recs in arms.items()
               for i, (r, x) in enumerate(((r, x) for r in recs for x in haiku(r, 1)["introduced_list"]), 1)}
    assert sorted(sum(AUDIT.values(), [])) == sorted(flagged), "audit labels must cover every flagged statement"
    provenance = claim_provenance()
    assert set(provenance) == set(flagged), "dated reassessment must cover every flag, including unresolved ones"
    out = {"note": "post hoc (after the pre-registered Exp08 analysis); exploratory",
           "drift": {a: drift(r) for a, r in arms.items()}, "per_pass": {a: per_pass(r) for a, r in arms.items()},
           "lstm_exclusion_sensitivity_2026_10_22": {a: lstm_sensitivity(r) for a, r in arms.items()},
           "introduced_reassessment_2026_10_22": {"counts": dict(Counter(v["status"] for v in provenance.values())),
                                                  "items": provenance},
           "introduced_audit_pass1": {"counts": {k: len(v) for k, v in AUDIT.items()},
                                      "status": "Historical AI-agent annotations; superseded by the dated reassessment, not verified truth labels.",
                                      "items": {k: {"id": flagged[k][0], "judge_text": flagged[k][1], "label": lab}
                                                for lab, ks in AUDIT.items() for k in ks},
                                      "sources": AUDIT_SOURCES}}
    (R / "exp08_posthoc.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "introduced_audit_pass1"}, indent=1))
    print(out["introduced_audit_pass1"]["counts"])


if __name__ == "__main__":
    main()
