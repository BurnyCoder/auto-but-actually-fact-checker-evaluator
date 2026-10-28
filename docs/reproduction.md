# Reproduce the saved analyses

The [verification record](../reports/verification_2026-10-28.md) recomputes the primary results from these records
and lists dated corrections and post-hoc sensitivity analyses. These commands use committed records and do not call models.
Run from the repository root after the [README setup](../README.md#quick-start):

```bash
uv sync --locked --all-groups
uv run --locked pytest
uv run --locked --group paper python reports/scripts/analyze_scifact.py
uv run --locked --group paper python reports/scripts/analyze_correction.py
uv run --locked --group paper python reports/scripts/analyze_ai_errors.py
uv run --locked --group paper python reports/scripts/exp08_posthoc.py
uv run --locked --group paper python -c "import typst; from pathlib import Path; p=Path.cwd(); typst.compile(p/'reports/paper/paper.typ', output=p/'reports/paper/paper.pdf', root=p)"
uv run --locked --group docs python docs/scripts/take_screenshots.py --offline --channel msedge
```

The analysis scripts rewrite their derived JSON and figures; review the diff afterward. They do not rewrite
frozen input datasets, cached model responses, or judge records. The hash regression checks the
[before-audit SHA-256 manifest](../reports/results/evidence_hashes_2026-10-22.json). Git attributes preserve these
files' exact bytes across platforms. PDF metadata, font rendering and image bytes can vary by runtime; the
numerical statistics are the quantities to compare. Figure 2 uses corrected medians, Figure 3 identifies missing
judgments, and Figure 4 labels partial-credit scores.

| Analysis | Available in a clean clone | Local-artifact limits |
|---|---|---|
| SciFact metrics, paired comparisons, retest | `reports/results/exp01*` through `exp05*` records | Full prompts and provider billing records are absent |
| Exp07 judge correctness and proposed-correction trajectory | `reports/results/exp07_correction_*` | Complete timing/token/call logs are absent |
| Exp07 verdict/correction comparison | `compare_verdict_correction.py` uses saved item judgments | Its cost/time comparison also requires the referenced ignored `runs/` artifacts |
| Exp08 primary scores, 47-annotation sensitivity, sourced reassessment | Frozen dataset, per-state judgments and provenance JSON | `exp08_posthoc.py` marks per-pass timing/cost unavailable if referenced local runs are missing |
| Exp00 example-key scoring | Summary in the experiment report | `score_examples.py` requires ignored `runs/` files; historical labels have dated qualifications in the answer key |
| Local ledger totals ($7.35 by 2026-10-22, $7.55 by 2026-10-28) | Dated verification record only | `logs/spend.jsonl` is private and not published |

The screenshot command requires installed Edge. Alternatively omit `--channel msedge` after
`uv run --group docs playwright install chromium`. Screenshot responses are synthetic fixtures, not measured
model quality. The scripts isolate their logs and runs under `.cache/offline_ui/` and test Run, continuation and
Stop with zero model calls. The ordinary `afc check`, `afc bench`, `afc correct-eval` and `afc ai-errors` commands
run new model work and are separate from the offline reconstruction above.
