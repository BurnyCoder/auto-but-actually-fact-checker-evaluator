# Benchmark design and pre-registration

This page was written **before** any paid benchmark call. Results go to [`reports/`](../reports). Any change to
this plan made after seeing data is marked *post hoc* in the reports.

## Question

Does the configurable rigorous prompt, run as a single `gpt-6-luna` API call with web search, judge scientific
claims more accurately than a simple single LLM call?

## Data

- **Dataset:** SciFact claims (Wadden et al., 2020, [arXiv:2004.14974](https://arxiv.org/abs/2004.14974)), loaded
  from the [HF parquet export](https://huggingface.co/datasets/allenai/scifact). They are expert-written
  biomedical claims labelled against a paper abstract.
- **Labels:** binary. SUPPORT = true and CONTRADICT = false. Claims labelled NEI and claims with conflicting
  evidence labels are dropped. NEI only means "this abstract does not address the claim", which is undefined for
  open-web checking.
- **Pool:** the validation and train splits (124 + 332 SUPPORT, 64 + 173 CONTRADICT). The test labels are hidden.
  No prompt or threshold is tuned on any of these items, so every pool item is held out.
- **Sample:** balanced (equal SUPPORT and CONTRADICT), seed 0, drawn with `bench/datasets.sample_balanced`.
- **Pilot:** a separately seeded handful of items (seed 999) measures cost per item. Pilot items are excluded from
  the main sample (`--exclude-from`) and are never analysed for accuracy.

## Systems (pre-specified, `configs/bench/`)

| id | prompt | search | everything else |
|---|---|---|---|
| A `baseline` | `minimal_baseline.md`: "Fact-check the following text." plus the minimal JSON contract (accuracy only) | off | gpt-6-luna, effort low, single API call |
| B `full_single_openai` | `rigorous_sections.md`, all default sections. Every label and condition is scored with a confidence. | hosted web_search, `max_tool_calls` 3, medium context, dataset hosts blocked | same |
| C `baseline_search` (Exp02) | as A | as B | same |

## Prediction rule and metrics (fixed in advance)

- `p_true = overall_accuracy_pct / 100`. If the overall score is missing, use the mean of the claim accuracies.
- Predict SUPPORT iff `p_true >= 0.5`.
- If no JSON summary can be parsed, even after repair, the item counts as **wrong**. A sensitivity analysis
  excluding these items is also reported.
- **Primary metric:** balanced accuracy (chance = 0.5).
- **Primary test:** exact McNemar on paired per-item correctness of B vs A, two-sided, α = 0.05.
- **Effect size:** Δ balanced accuracy (B − A) with a 95% paired-bootstrap percentile CI (10,000 resamples,
  seed 0).
- **Secondary metrics:** accuracy with Wilson 95% CI, macro-F1, AUROC and Brier score on `p_true`, parse
  failures, mean searches, cost.

## Hypotheses and falsification

- **H1:** B has higher balanced accuracy than A.
  - Supported if Δ > 0, the CI of Δ excludes 0, and McNemar p < 0.05.
  - Falsified (for this model and sample size) if Δ ≤ 0 or the CI includes 0.
  - A CI that includes 0 is reported as "no detectable difference", not as evidence of equality.
- **H2 (Exp02, secondary):** C vs A isolates the effect of web search alone. B vs C isolates the effect of the
  rigorous prompt given search. These are reported with the same statistics. They are not corrected for
  multiplicity and are labelled exploratory.

## Power and sample size

- **Formula:** McNemar power, Connor (1987): n = [z₀.₉₇₅√ψ + z₀.₈√(ψ − δ²)]² / δ².
- **What it gives:** for δ = 10 pp and a discordant fraction ψ = 0.2, n ≈ 155 at 80% power.
- **How n is chosen:** n is the largest balanced sample that fits the budget at the pilot's measured cost per
  item.
- **Budget:** about $5 for Exp01, inside the $10 cap for the whole project (checked before every call).
- **Reporting:** the achieved power is stated in the report.

## Threats to validity, and mitigations

- **Label leakage through search.** SciFact and its copies are online.
  - Mitigation: `blocked_domains` = huggingface.co, github.com, githubusercontent.com, kaggle.com,
    paperswithcode.com, allenai.org (OpenAI `filters.blocked_domains`).
  - Every consulted URL is logged, and items whose sources contain these hosts or "scifact" are flagged
    (`leak`) and counted.
- **Pretraining contamination.** SciFact (2020) is probably in the model's training data, which affects both
  systems.
- **Label semantics.** Gold labels are relative to one cited abstract. The open web may hold newer or
  conflicting evidence, so some disagreements with the gold label are not errors.
- **Construct validity.** SciFact CONTRADICT claims are often negations of a sentence in the source, so the
  benchmark partly measures retrieval.
- **Single run per item.** LLM sampling is stochastic, and McNemar ignores run-to-run variance. If the budget
  allows, the cheap baseline is re-run once to estimate test–retest agreement.
- **One model.** The results apply to `gpt-6-luna` at effort low. They are not claims about other models.

## Reproduce

```bash
uv run afc bench --systems configs/bench/baseline.json configs/bench/full_single_openai.json \
  --n 6 --seed 999 --max-cost 0.5 --out reports/results/exp01_pilot
uv run afc bench --systems configs/bench/baseline.json configs/bench/full_single_openai.json \
  --n N --seed 0 --exclude-from reports/results/exp01_pilot --max-cost 5 --out reports/results/exp01
```
