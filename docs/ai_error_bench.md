# Exp08 pre-registration — does iterative correction fix obviously wrong AI-research text?

Written and committed **before** the dataset was built and before any Exp08 correction or judge call. Results go to
`reports/experiments/exp08_ai_error_bench.md`. Anything decided after seeing data is marked *post hoc*. Wording
that was corrected later to match the code, without changing the plan, is marked *(clarified 2026-10-22)*.

## Why

Exp07 found the same observed correctness after one agent pass and after the loop on biomedical claims judged
against supplied abstracts; additional improvement was not detected. Two things limited that test:

- Each item was one scientific claim; within-claim error counts were not annotated.
- The gold was a related abstract, not the text itself.

Here real AI-research passages receive a known number of annotated edits, and the uncorrupted original is the
scoring reference. The historical design treated it as ground truth; the dated clarification below identifies
why that assumption and one error annotation are imperfect.

## Benchmark (`benchmarks/ai_errors_v1/`, built by `afc ai-errors build`)

**Passages: 20.**
- 10 Wikipedia lead sections: AlexNet, Transformer, GAN, BERT, GPT-3, RLHF, AlphaGo, Diffusion model, LSTM,
  ResNet.
- 10 arXiv abstracts: 1706.03762 (Transformer), 2106.09685 (LoRA), 2005.14165 (GPT-3), 2001.08361 (scaling laws),
  2203.15556 (Chinchilla), 2205.14135 (FlashAttention), 1810.04805 (BERT), 1512.03385 (ResNet), 2006.11239 (DDPM),
  2203.02155 (InstructGPT).
- Each is trimmed to whole sentences, at most ~180 words.
- Licences: Wikipedia CC BY-SA 4.0; arXiv metadata CC0 1.0 (each item links its paper and that paper's licence).

**Errors per passage, k:**
- A seeded (seed 0) shuffle of {0, 0, 1, 2, 2, 3, 3, 4, 4, 5}, done separately within each source *(clarified
  2026-10-22: the code shuffles this fixed multiset, `random.sample`, rather than drawing independently)*.
- That gives 24 errors per source and 48 in total.
- The 4 passages with k = 0 are **clean controls** that measure harm.

**Injection:**
- One `gpt-6-luna` API call per passage, using [`prompts/bench/inject_errors.md`](../prompts/bench/inject_errors.md).
- It proposes k single-fact edits as `{original_sentence, perturbed_sentence, error_type, false_fact, true_fact}`.
- Error types:
  - wrong number/year
  - wrong person/organisation
  - swapped entity
  - negation/reversed direction
  - absurd overclaim
- Code keeps an edit only if:
  - the original sentence is an exact substring (a near-copy with similarity ≥ 0.9 was later snapped to the
    passage's sentence; see the deviation in the [dataset README](../benchmarks/ai_errors_v1/README.md))
  - each sentence is used once
  - the change is real
  - the change is small (difflib ratio ≥ 0.5)
- The call is made up to 3 times in total until k edits validate *(clarified 2026-10-22: 3 attempts, not 3 retries)*.

**QC of every edit (before any correction run):**
- The AI coding agent that builds this repository reads every injected error *(clarified 2026-10-22: the QC was done
  by that agent, not by a human)*.
- Edits that are not objectively false, or could still be true, are replaced or dropped.
- Every decision is logged in the dataset README.
- The dataset is then frozen and committed.

## Systems

Both arms use the same agent, tools and passages; only the prompt differs.

**Agent:**
- Codex, `gpt-6-luna`, effort low.
- Live web search, at most 3 searches per pass.
- **No blocked hosts:** looking up the original Wikipedia page or arXiv abstract is legitimate fact-checking.
  How often the agent's sources include the original URL is reported.

**Arms:**
- **Naive** ([`configs/bench/ai_naive_codex.json`](../configs/bench/ai_naive_codex.json)): "Fact-check the
  following text." plus the minimal JSON contract with `corrected_text`.
- **Rigorous** ([`configs/bench/ai_rigorous_codex.json`](../configs/bench/ai_rigorous_codex.json)): the full
  default prompt.

**Forced 4 passes:**
- `accuracy_threshold` is 101, so the loop never self-stops, and there is no fixed-point stop.
- Pass p checks the text corrected by pass p − 1.
- A pass without a corrected text leaves the text unchanged; the loop then ends and the text is carried forward.
- State 0 is the corrupted input; states 1–4 are the text after each pass.

**Derived self-stop:**
- This is the answer the default loop (threshold 90%) would have given.
- It is the input of the first pass whose every claim is self-rated ≥ 90%, or state 4 if no pass qualifies.

## Scoring on a spectrum (reference judge)

[`prompts/judge/reference_errors.md`](../prompts/judge/reference_errors.md):

**Judge inputs:**
- the original passage
- the list of injected errors (wrong fact → true fact, corrupted sentence)
- the candidate text

The judge uses no web and no outside knowledge.

**Judge outputs:**
- Per injected error: `corrected` = 1, `partially` = 0.5 (removed, flagged or hedged, but the true fact not
  clearly restored), or `uncorrected` = 0.
- `introduced_errors`: statements that contradict the original or are plainly false.
- `overall_accuracy_pct`: 0–100.

**Metrics:**
- **Primary score per text:** `overall_accuracy_pct`.
- **Secondary:**
  - error fix rate (mean of 1 / 0.5 / 0 over injected errors)
  - introduced errors per text
  - net fixes = Σ fix − introduced

**Judges:**
- Primary: `claude-haiku-5-5`, the other model family from the corrector.
- Secondary: `gpt-6-luna`.
- Each distinct text is judged once per judge, so the corrupted input is judged twice per judge (once per arm).
  That gives a test-retest check.

**Validity (reported before H1–H3, from `analyze_ai_errors.py`; the gate below is checked from its output):**
- The original passage should score ≈ 100 with ≈ 0 introduced errors and its errors marked `corrected`.
- The corrupted input should have its errors marked `uncorrected`, and its score should fall with k (Spearman ρ < 0).
- A deterministic number check agrees with the judge's status on number/year errors. The check: the true number is
  present and the false number absent.
- **Gate:** if the primary judge scores originals below 90 on average, or its corrupted-input fix rate is above
  0.2, conclusions are flagged unreliable.

## Hypotheses and analysis

All of these use the primary judge, n = 20 passages paired across conditions, and
[`reports/scripts/analyze_ai_errors.py`](../reports/scripts/analyze_ai_errors.py). For each: Δ is the mean
difference, with a paired-bootstrap 95% CI (10,000 resamples, seed 0) and a Wilcoxon signed-rank p (Pratt zero
handling).

- **H1 (primary): do more passes help?**
  - Rigorous arm, score after 4 passes vs after 1.
  - Iteration *helps* if Δ > 0 and the CI excludes 0, and *harms* if Δ < 0 and the CI excludes 0; otherwise
    there is no detectable difference.
  - The same test for the naive arm (H1b) and with the secondary judge (robustness).
- **H2: does the rigorous prompt beat the naive one?** Rigorous vs naive after 1 pass (also reported after 4).
- **H3: does one pass help at all?** Each arm's pass 1 vs the corrupted input.
- **Harm:**
  - On the k = 0 controls: score and introduced errors per pass, and how many controls end up changed (Wilson CI).
  - Across all passages: introduced errors per pass.

**Descriptive:**
- score and fix-rate curves over passes 0–4 for both arms, with bootstrap CIs, in fig 4
- fix rate by error type and by k (cluster bootstrap by passage)
- the derived self-stop answer vs pass 1 and pass 4
- self-rated accuracy per pass
- judge agreement: Spearman ρ of scores, and number-check agreement
- searches and notional cost per passage

**What would falsify "iteration makes text better":** H1 Δ ≤ 0, or a CI that includes 0, in the rigorous arm.
Exp07 predicts this null.

**Power:**
- With n = 20 paired passages, α = 0.05 and power 0.8, only a standardised paired effect d_z ≳ 0.65 is
  detectable under the planning approximation n ≈ ((1.96 + 0.84) / d_z)² + 2 for a paired t-test.
  Actual Wilcoxon power depends on the paired-difference distribution; this was not an exact power calculation
  for that test (clarified 2026-10-22).
- The original plan interpreted a null H1 as "no large effect", not "no effect"; the dated methodological
  clarification below retracts that interpretation without changing the historical support rule.
- About 48 errors give finer, error-level fix-rate CIs, but those are clustered within passages, which the
  cluster bootstrap respects.

## Budget

**Billed (gpt-6-luna / claude-haiku-5-5 API):**
- about $0.01 for injection
- about 20 passages × 2 arms × ≤ 6 texts × 2 judges = ≤ 480 judge calls, about $0.2 in total
- JSON repair of agent output

**Not billed:** the Codex agent runs on the subscription; it is recorded as notional cost.

**Recorded-cost controls:** `--max-cost` checks billed + notional estimates for the invocation; the global
`SPEND_LIMIT_USD` checks recorded billed estimates. Calls can overshoot before their costs are recorded, and
unknown costs are not included. These are soft controls, not provider-enforced spending guarantees.

## Reproduce

```bash
uv run afc ai-errors build --out SCRATCH_DIR   # rebuilds an uncurated copy; the frozen dataset.jsonl also holds the QC edits
uv run afc ai-errors run --system configs/bench/ai_naive_codex.json --judges configs/bench/judge_haiku.json configs/bench/judge_luna.json --out reports/results/exp08_ai_errors --max-cost 10
uv run afc ai-errors run --system configs/bench/ai_rigorous_codex.json --judges configs/bench/judge_haiku.json configs/bench/judge_luna.json --out reports/results/exp08_ai_errors --max-cost 10
uv run --group paper python reports/scripts/analyze_ai_errors.py
```

## Methodological clarification — 2026-10-22

The [original committed plan](https://github.com/BurnyCoder/auto-fact-checker/blob/a2b7759/docs/ai_error_bench.md)
and its decision rules remain the historical record. “Falsified” above denotes failure to meet the support
criterion; neither nonsignificance nor the planned detectable effect size proves equality or excludes larger
effects ([ASA statement](https://doi.org/10.1080/00031305.2016.1154108)). The bootstrap interval estimates a mean
difference, whereas [Wilcoxon](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.wilcoxon.html)
tests the paired-difference distribution under its symmetry assumptions; these need not agree.

The frozen benchmark contains 48 annotated edits, not 48 independently established false facts. LSTM edit 3
changes “can last thousands” to “can last three” timesteps without an upper-bound qualifier; it is ambiguous.
Original passages also contain source inaccuracies, such as calling self-attention permutation-invariant.
See the [dataset erratum](../benchmarks/ai_errors_v1/README.md) and the
[dated post-hoc sensitivity](../reports/experiments/exp08_ai_error_bench.md#dated-reassessment--2026-10-22).
“Clean” means no injected edits, not verified error-free text. The original texts, judgments and primary
statistics are preserved; no candidate was changed or rejudged. The weighted error-fix score grants half
credit to removal/hedging and must not be described as the percentage of errors fully corrected.
