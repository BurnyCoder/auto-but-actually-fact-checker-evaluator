"""Score fact-checking runs on examples/*.md against examples/answer_key.json.

Usage: uv run python reports/scripts/score_examples.py RUN_ID_SUBSTRING:EXAMPLE_NAME [...]
Prints, per run, each key claim's matched accuracy and whether the binary verdict (accuracy >= 50) agrees with the
key, plus the run's agreement rate. Used for reports/experiments/exp00_ai_texts.md.
"""

import glob
import json
import sys

from auto_fact_checker.config import ROOT
from auto_fact_checker.results import FactCheckRun

KEY = json.loads((ROOT / "examples" / "answer_key.json").read_text(encoding="utf-8"))


def score(run: FactCheckRun, example: str) -> list[tuple[str, bool, float | None, bool | None]]:
    """(keyword, key truth, matched min accuracy, agrees) for every key claim of the example."""
    claims = run.iterations[0].final.summary.claims if run.iterations[0].final.summary else []
    rows = []
    for k in KEY[example]:
        accs = [c.accuracy_pct for c in claims if k["match"].lower() in c.claim.lower() and c.accuracy_pct is not None]
        acc = min(accs) if accs else None
        rows.append((k["match"], k["true"], acc, None if acc is None else (acc >= 50) == k["true"]))
    return rows


def main(args: list[str]) -> None:
    for arg in args:
        rid, example = arg.split(":")
        path = sorted(glob.glob(str(ROOT / "runs" / f"*{rid}*" / "run.json")))[-1]
        run = FactCheckRun.model_validate_json(open(path, encoding="utf-8").read())
        rows = score(run, example)
        agree = [r[3] for r in rows if r[3] is not None]
        print(f"{rid} ({example}): agreement {sum(agree)}/{len(rows)} (unmatched {sum(r[3] is None for r in rows)})")
        for kw, truth, acc, ok in rows:
            print(f"  {kw:28s} key={'T' if truth else 'F'} acc={acc} {'OK' if ok else 'MISS' if ok is False else 'n/a'}")


if __name__ == "__main__":
    main(sys.argv[1:])
