# Exp01 — Rigorous configurable prompt + web search vs. a simple LLM call on SciFact (pre-registered primary)

**Pre-registration:** [`docs/benchmark.md`](../../docs/benchmark.md). It was committed (PR #7, commit `378c59b`)
before any paid LLM call. **Data:** `reports/results/exp01_pilot/`, `exp01/`, `exp01_retest/`.
**Analysis:** [`reports/scripts/analyze_scifact.py`](../scripts/analyze_scifact.py), output in
`reports/results/scifact_analysis.json`. **Date:** 2026-10-17.

## Hypothesis and falsification criterion (from the pre-registration)

**H1:** system B (the full default rigorous prompt, with every label and condition scored with confidence, as one
`gpt-6-luna` API call with hosted web search) has higher **balanced accuracy** on binary SciFact than system A
(the same model, the minimal prompt "Fact-check the following text." plus the minimal JSON contract, no search).

H1 counts as supported only if all three hold:
- Δ = BA(B) − BA(A) > 0
- the 95% paired-bootstrap CI of Δ excludes 0
- the exact McNemar test gives p < 0.05

## Method

- **Data:**
  - SciFact claims with an unambiguous SUPPORT or CONTRADICT label (NEI and conflicting claims removed).
  - The pool is the validation and train splits; nothing was tuned on it.
  - The sample is balanced, n = 200 (100 / 100), seed 0, with the 6 pilot claims excluded.
- **Prediction:** `p_true = overall_accuracy_pct / 100`, and SUPPORT iff ≥ 0.5. Both were fixed in advance.
- **Systems:**
  - A = [`configs/bench/baseline.json`](../../configs/bench/baseline.json)
  - B = [`configs/bench/full_single_openai.json`](../../configs/bench/full_single_openai.json)
  - B settings: `max_tool_calls` = 3, `search_context_size` = medium, effort low, and the blocked domains
    huggingface.co, github.com, githubusercontent.com, kaggle.com, paperswithcode.com and allenai.org.
- **Sample size:** the pilot (6 claims, seed 999) measured $0.0165 per claim on average for B (max $0.0237) and
  $0.0003 for A. The pre-registered rule is "the largest balanced sample that fits the budget [about $5] at the
  pilot's measured cost per item". It was applied conservatively, at the pilot's worst-case cost, which allows about
  208 (with A's cost) and was rounded down to n = 200 (0.0237 × 200 = $4.74 for B); at the mean cost about 296
  would have fitted. Connor's McNemar formula needs n ≈ 155 for δ = 10 pp at ψ = 0.2 (α = 0.05 two-sided, 80%
  power).
- **Noise control:** A was run a second time on the same 200 items (test–retest).

## Results

| system | balanced accuracy | accuracy [95% Wilson CI] | SUPPORT recall | CONTRADICT recall | AUROC | Brier | parse failures | leak-flagged items | mean searches | cost (200 claims) |
|---|---|---|---|---|---|---|---|---|---|---|
| A simple call | **0.755** | 0.755 [0.691, 0.809] | 0.79 | 0.72 | 0.844 | 0.165 | 0 | 0 | 0 | $0.063 |
| B full prompt + search | **0.865** | 0.865 [0.811, 0.906] | 0.85 | 0.88 | 0.944 | 0.101 | 0 | 0 | 1.17 | $2.97 |

**Paired test (B − A, n = 200):**
- Δ balanced accuracy = **+0.110**, 95% paired-bootstrap CI **[+0.062, +0.160]**.
- Discordant pairs: A right & B wrong = 3, A wrong & B right = 25. Exact McNemar **p = 2.7 × 10⁻⁵**.

**H1 is supported:** all three criteria are met.

As a secondary metric, AUROC also improved: Δ = +0.099 [+0.052, +0.150] (paired bootstrap, 2,000 resamples).

**Sensitivity analyses:**
- Dropping parse failures (pre-registered) changes nothing: there were none.
- Dropping leak-flagged items (added post hoc; the pre-registration only says flags are counted) changes nothing:
  none were flagged; no consulted source matched a blocked host or "scifact".

**Test–retest of A** (same config, independent run):
- 96.5% of predictions identical.
- Retest balanced accuracy 0.760, Δ = +0.005 [−0.020, +0.031], McNemar 3 / 4, p = 1.0.

This describes one pair of baseline runs. Its item-bootstrap interval does not estimate variance across repeated
complete runs or a general generator noise floor.

Figures: [`reports/figures/fig1_balanced_accuracy.png`](../figures/fig1_balanced_accuracy.png) (balanced accuracy
with CIs) and [`fig2_scores_by_gold_label.png`](../figures/fig2_scores_by_gold_label.png) (score distributions by
gold label). B separates the classes more cleanly: median predicted accuracy 77 vs 11 for SUPPORT vs CONTRADICT,
against 80 vs 15 for A. A has a large cluster of CONTRADICT claims scored 65–95.

## Interpretation

- B's gain comes mostly from CONTRADICT claims (recall 0.72 → 0.88). These are SciFact's expert negations of
  abstract sentences, which a model without retrieval tends to accept as plausible.
- **This experiment cannot say whether the gain comes from the prompt or from search**, because B changes both.
  Exp02 (pre-registered) and Exp03 (post hoc) separate them. The answer is that search explains essentially all of
  it.
- The observed discordance ψ = 0.14 with δ = 0.11 implies the design had well over 80% power for an effect of
  this size. This is stated for context, not to interpret the significant result.

## Threats to validity

- **Contamination.** SciFact (2020) is probably in the pretraining data, which could inflate both systems; B still
  improved over A.
- **Leakage through search.** Dataset hosts were blocked and every source URL was checked: 0 flags. Blocking
  cannot catch unknown mirrors, so leakage cannot be fully ruled out.
- **Gold semantics.** Labels are relative to the cited evidence abstract(s). Some of B's "errors" may reflect newer or broader
  evidence; nothing was re-adjudicated.
- **External validity.** One model (`gpt-6-luna`, effort low), one biomedical claim dataset, single-sentence
  inputs. Multi-claim documents, other domains and other models were not tested.

## Learnings

- The pre-registered prediction rule needed no post-hoc changes: 0 of 400 calls failed to parse, and the tolerant
  parser plus repair step was never needed.
- Budget accuracy: projected $3.3 for B, actual $2.97. Searches averaged 1.17 per claim, below the cap of 3.
