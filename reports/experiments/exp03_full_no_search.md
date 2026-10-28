# Exp03 — Full rigorous prompt without web search (post hoc, completes the 2×2)

**Status:** post hoc and exploratory. It was decided after seeing the Exp01/Exp02 results and is not in the
pre-registration. **Data:** `reports/results/exp03_full_no_search/`. **System D:**
[`configs/bench/full_no_search.json`](../../configs/bench/full_no_search.json). **Date:** 2026-10-17.

## Why

Exp01 and Exp02 give three cells of a 2×2 design (prompt minimal/full × search off/on). D fills the fourth: the
full prompt without search. This tests whether the rigorous prompt helps when the model must rely on its own
knowledge, a setting where instructions such as "double check yourself" and "be sceptical" might matter more.

## Results (the same 200 items, gpt-6-luna, effort low, 1 call per claim)

| system | prompt | search | balanced accuracy | accuracy [Wilson 95%] | SUPPORT / CONTRADICT recall | AUROC | Brier | median score SUPPORT / CONTRADICT | billed cost |
|---|---|---|---|---|---|---|---|---|---|
| A | minimal | off | 0.755 | [0.691, 0.809] | 0.79 / 0.72 | 0.844 | 0.165 | 80 / 15 | $0.06 |
| D | full | off | 0.765 | [0.702, 0.818] | 0.75 / 0.78 | 0.891 | 0.142 | 68 / 20 | $0.44 |
| C | minimal | on | 0.890 | [0.839, 0.926] | 0.85 / 0.93 | 0.956 | 0.087 | 85 / 10 | $2.30 |
| B | full | on | 0.865 | [0.811, 0.906] | 0.85 / 0.88 | 0.944 | 0.101 | 77 / 11 | $2.97 |

| comparison (paired, n = 200) | Δ balanced accuracy [95% CI] | McNemar b / c, p | Δ AUROC [95% CI] (post hoc for every row) |
|---|---|---|---|
| D − A (prompt, no search) | +0.010 [−0.026, +0.047] | 6 / 8, 0.79 | +0.047 [+0.013, +0.082] |
| B − C (prompt, with search) | −0.025 [−0.061, +0.010] | 9 / 4, 0.27 | −0.012 [−0.032, +0.004] |
| C − A (search, minimal prompt) | +0.135 [+0.086, +0.186] | 2 / 29, 4.6×10⁻⁷ | +0.112 [+0.065, +0.163] |
| B − D (search, full prompt) | +0.100 [+0.055, +0.148] | 2 / 22, 3.6×10⁻⁵ | +0.053 [+0.021, +0.089] |

**Simple contrasts** (2×2, balanced accuracy; no factorial interaction test):
- Search: about +0.10 to +0.135, clearly non-zero under both prompts.
- Prompt: −0.025 to +0.010, not distinguishable from zero under either search setting.

## Interpretation

- **No verdict improvement from the rigorous prompt was detected in either search condition.** The intervals
  allow effects in both directions; this does not establish zero effects or rule out a prompt–search interaction.
- **Hypothesis-generating:**
  - Without search, the full prompt **improves ranking**: AUROC +0.047 [+0.013, +0.082] and Brier 0.165 → 0.142.
  - No improvement in thresholded verdicts was detected.
  - Its scores are less extreme. The median for SUPPORT drops from 80 to 68 and for CONTRADICT rises from 15 to
    20, consistent with more hedging.
  - This is 1 of 9 post-hoc comparisons (18 post-hoc tests counting Δ AUROC) and the CI lower bound is close to 0,
    so it needs a pre-registered
    replication before being claimed.
- **Retry note:** one item (train-341) first failed with an API stream error ("Didn't receive a
  `response.completed` event"). It was then the only parse failure and was scored wrong. That run also exposed the
  benchmark-caching bug fixed in the code-review pass (failed items were cached as final), and the item was re-run
  once after the fix. The numbers above use the re-run; before it, D was 0.760 / AUROC 0.888.

## Learnings

- Measuring both the threshold metric (balanced accuracy) and a ranking metric (AUROC) showed an effect that the
  primary metric hides.
- The full prompt without search costs $0.0022 per claim, 7× the minimal call, because of about 4,000 output
  tokens per claim.
