# Exp02 — Is it the search or the prompt? Simple prompt + web search (pre-registered secondary)

**Pre-registration:** H2 in [`docs/benchmark.md`](../../docs/benchmark.md). **Data:** `reports/results/exp02/`.
**Analysis:** [`reports/scripts/analyze_scifact.py`](../scripts/analyze_scifact.py). **Date:** 2026-10-17.

## Question

Exp01's system B changed two things at once relative to A: the prompt (rigorous, every condition scored) and
hosted web search. System C keeps A's minimal prompt and adds B's search settings:
- `max_tool_calls` 3
- medium context
- the same blocked domains

C − A therefore estimates the effect of **search alone**, and B − C estimates the effect of **the rigorous prompt
given search**. These comparisons were pre-specified as secondary. They are not corrected for multiplicity and are
labelled exploratory.

## Results (the same 200 items as Exp01)

| system | balanced accuracy | accuracy [95% Wilson CI] | SUPPORT recall | CONTRADICT recall | AUROC | Brier | mean searches | cost |
|---|---|---|---|---|---|---|---|---|
| A simple call | 0.755 | 0.755 [0.691, 0.809] | 0.79 | 0.72 | 0.844 | 0.165 | 0 | $0.063 |
| C simple + search | **0.890** | 0.890 [0.839, 0.926] | 0.85 | 0.93 | 0.956 | 0.087 | 1.03 | $2.30 |
| B full prompt + search | 0.865 | 0.865 [0.811, 0.906] | 0.85 | 0.88 | 0.944 | 0.101 | 1.17 | $2.97 |

| comparison | Δ balanced accuracy [95% paired bootstrap CI] | discordant (first right / second right) | exact McNemar p |
|---|---|---|---|
| C − A (search effect) | **+0.135 [+0.086, +0.186]** | 2 / 29 | 4.6 × 10⁻⁷ |
| B − C (rigorous prompt given search) | **−0.025 [−0.061, +0.010]** | 9 / 4 | 0.27 |

## Interpretation

- **Web search explains the whole Exp01 improvement.** Adding search to the simple prompt gives +13.5 pp of
  balanced accuracy, with the CI well away from 0.
- **There is no detectable benefit of the long rigorous prompt on this task.** The point estimate is negative
  (−2.5 pp) and the CI [−6.1, +1.0] includes 0, so we cannot claim it hurts either.
- What the CI does rule out: a gain of more than about 1 pp from the rigorous prompt for single-claim binary
  verification with `gpt-6-luna`.
- **Cost.** B costs 29% more than C ($2.97 vs $2.30) and produces far longer outputs: 3,562 output tokens per claim on average, vs 420 for C (8.5×),
  because it scores 45 labels and 12 conditions with confidences.
- **Scope of the conclusion.** SciFact measures only the binary truth of single, atomic, mostly empirical claims.
  The rigorous prompt exists to produce things this benchmark does not score:
  - nuance and labels (overgeneralizing, overstated, …)
  - the condition assessments
  - corrected text, issue lists, perspectives

  "No accuracy gain on SciFact" is therefore not "no value". It is evidence that, for the binary-verdict part of
  the job, the prompt's extra instructions do not improve the verdict.
- **A plausible mechanism (untested).** Spreading the output budget across 57 scored dimensions may dilute
  attention to the core verdict. B used slightly more searches (1.17 vs 1.03), so less search was not the cause.

## Learnings

- Prompt complexity is not free. On a narrow accuracy metric it can be neutral or slightly negative, while it
  costs tokens and latency.
- In the UI, users can switch off every block. The L1-style "search + minimal prompt" configuration is the
  measured best accuracy-per-dollar setting for binary verification. Presets are kept unchanged because the
  rigorous blocks serve the qualitative outputs.
