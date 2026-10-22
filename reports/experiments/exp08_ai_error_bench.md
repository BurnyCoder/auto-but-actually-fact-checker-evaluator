# Exp08 — Does iterative correction fix obviously wrong AI-research text?

**Pre-registration:** [`docs/ai_error_bench.md`](../../docs/ai_error_bench.md). It was committed (PR #19) before the
dataset was built and before any correction or judge call, together with the analysis script
[`reports/scripts/analyze_ai_errors.py`](../scripts/analyze_ai_errors.py), which was not changed afterwards.

**Data:**
- benchmark: [`benchmarks/ai_errors_v1/`](../../benchmarks/ai_errors_v1), frozen in PR #20 before any correction run
- records: `reports/results/exp08_ai_errors/ai_{naive,rigorous}_codex.jsonl`
- analysis: `reports/results/ai_errors_analysis.json`
- post hoc: `reports/results/exp08_posthoc.json`, from [`exp08_posthoc.py`](../scripts/exp08_posthoc.py)
- figure: [`fig4_ai_errors_passes.png`](../figures/fig4_ai_errors_passes.png)

**Date:** 2026-10-17.

## Question

Can a fact-checking agent repair text about AI research that contains obviously wrong claims? Does running the
correction several times make the text better than running it once? Does a long rigorous prompt beat a naive
"Fact-check the following text." prompt?

## Method (as pre-registered)

**Benchmark.**
- 20 real passages: 10 Wikipedia lead sections and 10 arXiv abstracts about AI research (AlexNet, Transformer,
  GPT-3, RLHF, ResNet, LoRA, Chinchilla, …). Each is 107–180 words.
- Each passage got k ∈ {0, …, 5} injected errors (seed 0, same k distribution per source), 48 errors in total.
- The 4 passages with k = 0 are clean controls.
- Each error changes one checkable fact. Types:
  - wrong number/year: 15
  - swapped entity: 13
  - negation/reversal: 11
  - absurd overclaim: 5
  - wrong person/organisation: 4
- One `gpt-6-luna` call proposed each passage's errors; code validated them.
- The AI coding agent that builds this repository (not a human) read all 48 as word diffs and edited 6: 4 repairs
  and 2 type relabels (log in the dataset README). Examples of injected errors: 2012 → 2022, 175 billion →
  175 million parameters, 28.4 → 284 BLEU, CIFAR-10 → CIFAR-100, "does not inherently make them better" →
  "inherently makes them better".

**Arms.**
- **Agent:** Codex (`gpt-6-luna`, effort low), live web search with at most 3 searches per pass.
- **Hosts:** none blocked; finding the source is legitimate fact-checking.
- **Prompts:**
  - *Naive:* "Fact-check the following text." plus the minimal JSON contract with `corrected_text`.
  - *Rigorous:* the full default prompt.
- **Forced 4 passes:** pass p checks pass p − 1's corrected text. State 0 is the corrupted input.
- **Derived self-stop:** the answer the default loop (threshold 90%) would have returned.

**Scoring on a spectrum.**
- A reference judge gets the original passage, the injected errors (wrong → true fact) and a candidate text, and
  uses no web.
- It returns:
  - a status per injected error: corrected = 1, partially = 0.5, uncorrected = 0
  - "introduced errors"
  - `overall_accuracy_pct` (0–100), the **primary score**
- Primary judge: `claude-haiku-5-5`, cross-family. Secondary judge: `gpt-6-luna`.
- Paired over the 20 passages: mean Δ with a paired-bootstrap 95% CI, and Wilcoxon signed-rank (Pratt).
- Error-level rates use a cluster bootstrap by passage.

## Validity (gate passed)

| check | Haiku (primary) | Luna |
|---|---|---|
| original passage: mean score (min) | 99.1 (80) | 100 (100) |
| original passage: errors marked corrected / introduced errors | 0.98 / 0 | 1.00 / 0 |
| corrupted input: errors marked corrected | 0.00 | 0.00 |
| corrupted input: mean score for k = 0 / 1 / 2 / 3 / 4 / 5 | 100 / 66 / 39 / 13 / 7.5 / 7.5 | 100 / 94 / 81 / 76 / 60 / 60 |
| Spearman ρ (k, corrupted-input score) | −0.81 (p = 3 × 10⁻¹⁰) | −0.92 (p = 2 × 10⁻¹⁷) |
| test–retest: the same corrupted text judged in both arms, mean \|Δ\| | 3.9 points | 4.5 points |

**Gate:** originals ≥ 90 and corrupted-input fix rate ≤ 0.2. Both held (checked from the `validity` fields of
`ai_errors_analysis.json`; the script does not apply the gate itself).

**Further checks:**
- A deterministic number check (true number present ∧ false number absent) agrees with Haiku's per-error status on
  85% of 140 number-error states (κ = 0.66).
- The judges rank texts similarly (Spearman 0.70 over 232 texts) but Haiku is much harsher: a mean absolute
  difference of 13.9 points (Haiku 13.7 points lower on average), largest on corrupted text.

## Results

![fig4](../figures/fig4_ai_errors_passes.png)

**Fig. 4.** Mean score and mean per-error fix score after each pass, with 95% bootstrap bands (n = 20 passages,
48 errors). Pass 0 is judged separately in each arm, hence 40.0 vs 38.6.

| primary judge (Haiku) | naive prompt | rigorous prompt |
|---|---|---|
| score: corrupted input → pass 1 → 2 → 3 → 4 | 38.6 → **90.4** → 89.4 → 88.7 → 89.4 | 40.0 → **85.7** → 84.4 → 85.4 → 86.2 |
| injected errors fixed (mean of 1 / 0.5 / 0), pass 1 → 4 | 0.958 → 0.969 | 0.969 → **0.896** |
| fully corrected errors, pass 1 → 4 (of 48) | 44 → 45 | 45 → **38** |
| introduced errors per passage, pass 1 → 4 | 0.40 → 0.40 | 0.70 → 0.45 |
| self-rated accuracy of the text checked, pass 1 → 4 | 68 → 98 | 64 → 96 |
| time / output tokens per pass | 18 s / 1.5k | 110 s / 18k |
| notional agent cost per passage (4 passes; with billed judges) | $0.093 ($0.096) | $0.132 ($0.137) |

**H3 — one pass helps a lot (supported in both arms).**
- *Naive:* corrupted input → pass 1 Δ = **+51.8 [+34.1, +68.9]**, Wilcoxon p = 0.0007.
- *Rigorous:* Δ = **+45.8 [+28.8, +61.9]**, p = 0.0009.
- The 4 passages that got worse are the 4 clean controls.
- One pass fixed 96–97% of the injected errors.

**H1 — more passes do not help (primary: no detectable difference).**
- *Rigorous*, pass 4 vs pass 1: Δ = **+0.45 [−4.55, +4.80]** (10 better, 8 worse, 2 same), p = 0.43.
- *Naive:* Δ = −1.0 [−6.75, +5.30], p = 0.13.
- *Luna judge* (robustness): rigorous +2.2 [−0.25, +4.75]; naive −1.55 [−3.60, +0.45]. Both CIs include 0.
- *Net fixes* (Σ fix − introduced): rigorous +0.08 [−0.35, +0.48], naive +0.03 [−0.33, +0.40].
- **Reading:** the falsification condition (Δ ≤ 0, or a CI that includes 0) is met, so the data do not support
  "iteration makes text better". At n = 20, effects of about d_z < 0.65 cannot be excluded.

**Secondary (pre-registered): iteration erodes fixes under the rigorous prompt.**
- Per-passage fix rate, pass 4 vs 1: **−0.067 [−0.117, −0.022]**. 6 of 16 passages are worse and none better,
  p = 0.015.
- The naive prompt holds its fixes: +0.006 [0.000, +0.019].
- By error type (rigorous, pass 1 → 4):
  - numbers 0.97 → 0.87
  - person/organisation 1.00 → 0.88
  - absurd overclaims 1.00 → 0.90
  - negations 0.91 → 0.86
  - swapped entities 1.00 → 0.96

**H2 — the rigorous prompt does not beat the naive one.**
- Pass 1: rigorous − naive = **−4.65 [−10.15, +1.80]**. 3 passages better, 16 worse; Wilcoxon p = 0.017.
- Pass 4: −3.2 [−8.4, +1.75], p = 0.29.
- The bootstrap CI includes 0, so the pre-registered reading is no detectable difference. The signed-rank test
  says the rigorous arm scores consistently, if slightly, lower.
- The rigorous arm also costs 6× the time and 12× the output tokens per pass.

**Harm on clean controls (k = 0, n = 4).**
- Every control was rewritten in every pass by both arms (4/4, Wilson [0.51, 1.00]).
- Haiku score after pass 1: 85.3 (rigorous) and 92.5 (naive). After pass 4: 83.0 and 91.3.
- Introduced errors per control per pass: 0.25–1.

**Derived self-stop.**
- The loop would have stopped at pass 2 (returning pass 1's text) for 17/20 (naive) and 12/20 (rigorous) passages.
- Its answer equals pass 1 in score: naive Δ 0.0 [−1.5, +1.5], rigorous +1.45 [−0.35, +3.55].
- Self-rated accuracy jumped to 95–98 after one pass and stayed there, whatever the judge said.

**Sources.**
- Both arms found the original arXiv abstract for 10/10 arXiv passages and cited Wikipedia for 0/10 Wikipedia
  passages. They preferred primary sources (NeurIPS/arXiv papers, OpenAI and Microsoft announcements).
- About 8 searches per passage over 4 passes.

## Post-hoc analyses (after seeing the results; exploratory)

**1. What the rigorous loop does to fixed errors.**
- No fixed error ever reverted to the false fact (0 transitions to "uncorrected").
- The 7 lost fixes all went corrected → *partially*: the true fact was hedged or deleted. Example: "experiments on
  two machine translation tasks" disappears; "Transformers are based on multi-head attention" becomes "commonly
  use attention … alongside feed-forward layers".
- The passage grows **157 → 176 → 207 → 234 → 254 words** (+62%). Naive: 157 → 150 → 168 → 181 → 191.
- Counts of 8 hedge words rise 10 → 56 (naive 10 → 41).
- All 20 passages were rewritten in every pass in both arms.
- This is the same hedging drift as in Exp07, now measured per fact.

**2. None of the "introduced errors" is clearly an error.**
The AI coding agent checked every statement the primary judge flagged after pass 1 (8 naive, 14 rigorous) against
the primary paper. Sources are in `exp08_posthoc.py`.

| flagged statements (pass 1, n = 22) | count | examples |
|---|---|---|
| genuinely false | **0** | – |
| true per the primary source, absent from or conflicting with the reference | **13** | AlexNet "500,000 neurons" (the NeurIPS abstract page says 500,000, the PDF and Wikipedia 650,000; first classified as false, corrected 2026-10-22); "10.9 points" ahead of the runner-up (26.2 − 15.3; Wikipedia: "more than 10.8"); the Transformer paper's Results section says **41.0** BLEU while its abstract says 41.8; parsing F1 91.3 / 92.7; ResNet's CIFAR-10 nets have **110 and 1202** layers (abstract: "100 and 1000"); Chinchilla is *not* uniformly better (it loses on 4 MMLU and 4 BIG-bench tasks); self-attention is permutation-*equivariant* |
| hedge or scope qualification of a reference claim | 9 | "does not establish general superiority", "attention weights do not measure token importance" |

The corrector, using primary sources, sometimes found inconsistencies in the source passages themselves. The
reference judge counts these against it. This happened despite its instruction that correct extra details are not
errors.

## Interpretation

1. **One correction pass does almost all the work.** With web search, the agent fixed 96–97% of the obvious
   injected errors in one pass and raised the score from about 40 to 86–90 (H3). Exp07 found one pass gave the
   whole gain on SciFact claims too, but repaired only about half of the false claims. Obvious single-fact errors
   in famous AI papers are far easier to repair than subtle biomedical claims.
2. **Iterating does not make the text better** (H1, both prompts, both judges). Under the rigorous prompt it makes
   the text *less specific*:
   - correct facts restored in pass 1 are hedged or dropped later (fix rate −0.067)
   - the text grows 62% longer
   - the loop's self-rating stays at 96%

   No fixed injected error ever reverted to its false value; the measured loss is hedging and deletion. Statements
   the judge flagged as introduced after pass 1 were audited (none clearly false); those after passes 2–4 were not.
3. **The naive prompt is at least as good and far cheaper** (H2). This agrees with Exp02 (SciFact verdicts): the
   long rigorous prompt adds cost, not accuracy. Here it also adds text that a reference-based judge penalises.
4. **Clean text is never left alone.** All 4 controls were rewritten in every pass, and their reference-based
   score fell 8–15 points. But the audit (post hoc, pass 1) suggests the "harm" is true additions and hedges, not
   false statements.
5. **Measurement caveat.** The holistic score measures faithfulness to the original passage, not truth.
   - Correctors with web search add true, more precise details and get penalised for it.
   - The per-error fix score is the cleaner measure. It gives the same answer: one pass ≈ 0.96–0.97; after four
     passes 0.969 (naive, +0.01) and 0.896 (rigorous, −0.07).

## Deviations from the pre-registration

**Dataset construction (all before any correction data):**
- Near-copied sentences (similarity ≥ 0.9) are snapped to the passage's own sentence.
- 6 of 48 injected edits were edited in QC, as planned: 4 repaired, 2 relabelled.
- Error-type labels were normalised.

**Analysis:**
- The smoke test (1 passage × 2 arms) is reported nowhere in the results; it only checked the pipeline.
- The pre-registered fix rate by k was computed (`ai_errors_analysis.json` → `by_k`) without the cluster-bootstrap
  CIs and is not reported here. Fix rates by error type have cluster CIs in `by_error_type` but are listed below
  without them.
- The validity gate was checked separately against the script's output (the script reports the inputs, not the
  verdict).
- Post-hoc audit: the AlexNet "500,000 neurons" statement was first classified as false and reclassified on
  2026-10-22 as a primary-source inconsistency (see the audit table).

## Limitations

- **Small n.** 20 passages give power only for large per-passage effects (d_z ≳ 0.65). The error-level analyses
  rest on 48 errors clustered in 16 passages.
- **Synthetic, obvious errors.** Each changes one fact in famous, heavily cited sources. Real-world errors (subtle
  misreadings, overgeneralisations) are harder; see Exp07.
- **Contamination.** The passages and papers are almost certainly in the model's pretraining data, and the agent
  also found the arXiv abstracts online. The benchmark measures repair *with* the answer reachable, not detection
  from first principles.
- **Same model family.** `gpt-6-luna` both injected and corrected the errors, which could make the edits easier
  for it to spot.
- **Reference-based judging penalises true additions** (post-hoc audit above). The holistic score likely
  underestimates accuracy when correctors add true details, and the rigorous arm, which writes more, is penalised
  more. The judge can also miss errors, so the score is not a strict bound either way.
- **QC and audit by an AI agent.** The dataset QC and the introduced-error audit were done by the AI coding agent
  that builds this repository, not by a human expert.
- **One corrector run per arm**, with no corrector test–retest; one model at low effort.
- **Crude hedge count.** The hedge-word count is a fixed 8-word list.

## Learnings

- Run one correction pass. Further passes are not neutral: with a long rigorous prompt they trade specific
  correct facts for hedges while the self-rating says 96%.
- A reference-based judge must be audited. Here all 22 "introduced errors" after pass 1 were true statements
  (13, one of them matching only part of the primary source) or hedges (9).
- Injecting errors with an LLM needs a QC step: 4 of 48 edits were incoherent, multi-fact or still true ("more than
  seven" → "more than three orders of magnitude"), and 2 more had the wrong error-type label.
