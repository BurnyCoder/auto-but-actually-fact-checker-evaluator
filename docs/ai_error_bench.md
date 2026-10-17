# Exp08 pre-registration — does iterative correction fix obviously wrong AI-research text?

Written and committed **before** the dataset was built and before any Exp08 correction or judge call. Results go to
`reports/experiments/exp08_ai_error_bench.md`. Anything decided after seeing data is marked *post hoc*.

## Why

Exp07 found that, on single-sentence biomedical claims judged against one abstract, one agent correction pass
gave the whole gain and further passes added nothing. Two things limited that test:

- Each claim held at most one error.
- The gold was a related abstract, not the text itself.

Here every passage is real AI-research text with a **known number of known errors**, and the uncorrupted original
is the ground truth. That allows scoring corrections on a spectrum and separating *fixing* injected errors from
*introducing* new ones, pass by pass.

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
- Drawn with seed 0 from {0, 0, 1, 2, 2, 3, 3, 4, 4, 5} independently within each source.
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
  - the original sentence is an exact substring
  - each sentence is used once
  - the change is real
  - the change is small (difflib ratio ≥ 0.5)
- The call is retried up to 3 times until k edits validate.

**Manual QC (before any correction run):**
- I read every injected error.
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

**Validity (reported before H1–H3, from `analyze_ai_errors.py`):**
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
  detectable. That is n ≈ ((1.96 + 0.84) / d_z)² + 2 for a paired t-test; Wilcoxon has a similar requirement.
- So a null H1 is "no large effect", not "no effect".
- About 48 errors give finer, error-level fix-rate CIs, but those are clustered within passages, which the
  cluster bootstrap respects.

## Budget

**Billed (gpt-6-luna / claude-haiku-5-5 API):**
- about $0.01 for injection
- about 20 passages × 2 arms × ≤ 6 texts × 2 judges = ≤ 480 judge calls, about $0.2 in total
- JSON repair of agent output

**Not billed:** the Codex agent runs on the subscription; it is recorded as notional cost.

**Cap:** each `afc ai-errors run` invocation is capped with `--max-cost` (billed + notional), on top of the
global `SPEND_LIMIT_USD` = $10 cap.

## Reproduce

```bash
uv run afc ai-errors build --out benchmarks/ai_errors_v1
uv run afc ai-errors run --system configs/bench/ai_naive_codex.json --judges configs/bench/judge_haiku.json configs/bench/judge_luna.json --out reports/results/exp08_ai_errors --max-cost 10
uv run afc ai-errors run --system configs/bench/ai_rigorous_codex.json --judges configs/bench/judge_haiku.json configs/bench/judge_luna.json --out reports/results/exp08_ai_errors --max-cost 10
uv run --group paper python reports/scripts/analyze_ai_errors.py
```
