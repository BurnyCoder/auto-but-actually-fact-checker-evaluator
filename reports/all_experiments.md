# All experiments — summary, glossary and results table

The detailed reports are in [`experiments/`](experiments), the paper in [`paper/`](paper), and the raw per-item data
in [`results/`](results). Every number here comes from `results/scifact_analysis.json`, the
`results/*/results.md` files, or the run records cited in each report.

## One-paragraph summary

- **System.** A configurable fact-checker where every block of a long "rigorous scientific fact-check" prompt is a
  UI toggle. It can run as one API call, as one agent (Codex / Claude Code), as an agent with subagents, or as
  separate calls per claim and per scientist.
- **Exp00.** On three AI-themed texts with planted errors, every preset agreed with a pre-written answer key on all
  42 claim verdicts (8 runs). This is a functional check; the errors are textbook.
- **Exp01.** On a pre-registered SciFact benchmark (n = 200 balanced claims, `gpt-6-luna`), the full prompt with
  web search beat a simple single call: balanced accuracy **0.865 vs 0.755**, Δ = +0.110 [+0.062, +0.160],
  McNemar p = 2.7 × 10⁻⁵.
- **Exp02.** The pre-registered ablation found a gain from **adding web search to the simple prompt**:
  - the simple prompt with search reached 0.890 (Δ vs baseline +0.135)
  - no positive effect of the long prompt was detected given search (−0.025 [−0.061, +0.010], p = 0.27) while
    costing 29% more and producing 8.5× more output tokens
- **Noise.** Test–retest of the baseline agreed on 96.5% of predictions (Δ +0.005 [−0.020, +0.031]).
- **Exp03** (post hoc): the full prompt without search scored 0.765 versus 0.755 for the simple call;
  no verdict improvement was detected in either search condition. Its observed ranking was higher (AUROC +0.047
  [+0.013, +0.082]); this is exploratory.
- **Exp04** (post hoc): a Codex agent running the full prompt reached 0.876 on 40 claims; no balanced-accuracy
  difference from the single API calls was detected. The intervals allow meaningful differences.
- **Exp05** (post hoc): a Claude Code agent (Haiku) running the full prompt ranked claims well (AUROC 0.962, below
  B's 0.978 and C's 0.992 on the same 40 claims) but was sceptical: SUPPORT recall 0.65, balanced accuracy 0.797. It
  differs in model as well, and one bio-safety refusal was scored wrong.

- **Exp07** (pre-registered): is text the correct-until-labelled-accurate loop calls "correct" actually correct?
  Setup: a Codex agent with web search looped on 100 SciFact claims (≤ 20 passes), judged against the gold
  evidence abstract(s) by Claude Haiku (93% accuracy on originals).
  - It raised gold-correctness from **49% to 62%** (Δ +0.13 [+0.02, +0.24], p = 0.035).
  - It labelled **100%** of its answers correct while only **62%** [52, 71] were.
  - Passes after the first correction had no detectable improvement (61% → 62%, Δ CI [−0.06,+0.08]).
  - It harmed 20% of originally correct claims; the sceptical checker rewrote 44 of 54 true claims.
  - Optional Claude Code subagent loop (n = 3, stopped early): it never labelled anything correct in 20 passes,
    while both judges found its final texts correct on 2 of 3 claims (the third was refused). Neither loop's
    stopping signal tracks truth.
- **Exp08** (pre-registered): our own benchmark of obviously wrong AI-research text. Setup: 20 Wikipedia/arXiv
  passages with 0–5 annotated edits (48 in total; one later identified as ambiguous), a Codex agent with web search, forced 4 passes, naive vs
  rigorous prompt, scored 0–100 against the original passage by a Haiku judge.
  - **One pass** fully corrected 44/48 and 45/48 annotated edits per the judge; half-credit weighted scores were
    0.958–0.969. Whole-text scores rose from about 40 to 86–90 (Δ +46 to +52, p < 0.001).
  - **No further mean-score gain was detected** in either arm (rigorous Δ +0.45 [−4.6, +4.8]). Under the rigorous prompt they
    eroded fixes (fix rate −0.067 [−0.117, −0.022]). Post hoc: the lost fixes were hedged or dropped correct facts,
    and the pass-4 text was 62% longer than the original reference on average.
  - **The naive arm had a higher observed mean** (pass 1: 90.4 vs 85.7, Δ −4.65 [−10.2, +1.8], Wilcoxon p = 0.017)
    at 1/6 of the time. Equivalence and noninferiority were not established.
  - Clean controls were always rewritten.
  - Dated post-hoc reassessment of 22 judge flags: 10 supported details, 3 source conflicts, 5 qualified
    inferences and 4 unresolved statements. The item-level AI-agent assessment is linked from the Exp08 report.

## Glossary (plain language)

| term | meaning |
|---|---|
| claim | one checkable statement, e.g. "GPT-3 has 175 billion parameters" |
| SciFact | a dataset of about 1.4k scientific claims with SUPPORT, CONTRADICT and insufficient-evidence outcomes; this project selects the first two with one or more annotated evidence abstracts ([paper](https://aclanthology.org/2020.emnlp-main.609/)) |
| balanced accuracy | the average of "share of true claims called true" and "share of false claims called false"; 0.5 = coin flip, 1.0 = perfect, whatever the class balance |
| recall (per class) | of all claims of one class, the share the system labelled correctly |
| AUROC | probability that a random true claim gets a higher accuracy score than a random false claim, ties counting half (uses the full 0–100 score, not just the 50% cut-off) |
| Brier score | mean squared error of a probability prediction; here the historical computation uses accuracy_pct/100 as a probability proxy, without establishing calibration (0 = perfect, 0.25 = always saying 50%) |
| Wilson CI | a 95% confidence interval for a proportion that behaves well near 0 and 1 |
| paired bootstrap CI | resample the same items for both systems (10,000 times for Δ balanced accuracy, 2,000 for Δ AUROC); the middle 95% of the resampled differences is the interval. Fig. 1's per-system CIs use 5,000 unpaired resamples |
| McNemar test | a test that looks only at items where the two systems disagree. In "X − Y: b / c", b = only Y (the subtracted system) is right and c = only X is right; exact version = binomial test on b vs c |
| pre-registered | study hypothesis, metric, test and decision rule committed before collecting that experiment's model outputs |
| post hoc | decided after seeing data; exploratory, weaker evidence |
| test–retest | running the same system twice to observe differences; one pair does not characterize variation across repeated full runs |
| leakage | the system finding the benchmark's answers (e.g. the dataset itself) online; mitigated by blocking dataset hosts and flagging any source URL that hits them |
| contamination | the benchmark being in the model's training data |
| confidence_pct | the model's self-reported confidence (0–100%); no calibration or general uncertainty identity is established |
| agent | an LLM that runs in a loop with tools (web search, shell) until it finishes, here Codex CLI or Claude Code |
| subagent | an agent started by another agent for a sub-task (e.g. one claim) |
| injected edit | a deliberate change intended to introduce an error; the annotation still needs factual and logical validation |
| reference judge | an LLM that scores a corrected text against the original, uncorrupted passage (Exp08) |
| fix score | per injected error: 1 = corrected, 0.5 = removed or hedged without restoring the true fact, 0 = still wrong |
| clean control | a passage with no injected edits; a change is not by itself factual harm, and the source may contain errors |
| Wilcoxon signed-rank test | a paired test on the signs and ranks of per-item differences; it does not assume normality |
| hedging drift | repeated rewriting that replaces specific facts with vaguer, qualified statements |

## Systems ("configurations") and results

All systems except F use `gpt-6-luna` (OpenAI, $0.10/$0.50 per 1M tokens; web search $0.01 per call); all use
reasoning effort low. Each takes one claim as input and returns a 0–100 accuracy score; the prediction is SUPPORT iff the score is
≥ 50.

| id | architecture | prompt | search | data | n | balanced accuracy | AUROC | Brier | cost | status |
|---|---|---|---|---|---|---|---|---|---|---|
| A | 1 API call | minimal ("Fact-check the following text." + JSON) | none | SciFact binary | 200 | 0.755 | 0.844 | 0.165 | $0.06 | pre-registered (Exp01) |
| A′ | same as A, re-run | minimal | none | same items | 200 | 0.760 | – | – | $0.06 | pre-registered noise control |
| B | 1 API call | full rigorous (23 of 24 blocks, NeurIPS role off by default; 45 labels + 12 conditions scored with confidence) | hosted web_search ≤3 calls, dataset hosts blocked | same | 200 | 0.865 | 0.944 | 0.101 | $2.97 | pre-registered (Exp01) |
| C | 1 API call | minimal | as B | same | 200 | 0.890 | 0.956 | 0.087 | $2.30 | pre-registered secondary (Exp02) |
| D | 1 API call | full rigorous | none | same | 200 | 0.765 | 0.891 | 0.142 | $0.44 | post hoc (Exp03) |
| E | Codex CLI agent | full rigorous | live web search (≤3 stated in prompt) | first 40 of the same items | 40 | 0.876 | 0.917 | 0.113 | $0 billed ($0.91 notional) | post hoc (Exp04) |
| F | Claude Code agent, **claude-haiku-5-5** | full rigorous | WebSearch/WebFetch (≤3 stated in prompt) | same 40 items | 40 | 0.797 | 0.962 | 0.161 | $0 billed ($1.27 notional) | post hoc (Exp05) |

| comparison | n | Δ balanced accuracy [95% CI] | McNemar b / c, p | Δ AUROC [95% CI] | reading |
|---|---|---|---|---|---|
| B − A | 200 | +0.110 [+0.062, +0.160] | 3 / 25, 2.7 × 10⁻⁵ | +0.099 [+0.052, +0.150] | H1 supported (pre-registered primary) |
| C − A | 200 | +0.135 [+0.086, +0.186] | 2 / 29, 4.6 × 10⁻⁷ | +0.112 [+0.065, +0.163] | search alone helps (pre-registered) |
| B − C | 200 | −0.025 [−0.061, +0.010] | 9 / 4, 0.27 | −0.012 [−0.032, +0.004] | no detectable benefit of the rigorous prompt given search (pre-registered) |
| A′ − A | 200 | +0.005 [−0.020, +0.031] | 3 / 4, 1.0 | – | one paired retest; repeated-run variance not estimated |
| D − A | 200 | +0.010 [−0.026, +0.047] | 6 / 8, 0.79 | +0.047 [+0.013, +0.082] | prompt without search: no verdict gain, maybe better ranking (post hoc) |
| B − D | 200 | +0.100 [+0.055, +0.148] | 2 / 22, 3.6 × 10⁻⁵ | +0.053 [+0.021, +0.089] | search helps under the full prompt too (post hoc) |
| E − A / B / C | 40 | +0.051 / −0.029 / −0.059, every CI spans 0 | 2/4 · 2/1 · 3/1 | – | no detected difference at n = 40; no equivalence test (post hoc) |
| F − A / B / C / E | 40 | −0.028 / −0.109 / −0.138 [−0.250, −0.045] / −0.079 | 6/4 · 7/2 · 6/0 (p = 0.031) · 7/3 | +0.073 / −0.017 / −0.031 / +0.045 | Claude agent: sceptical; ranks above A and E, below B and C; vs C nominal only (1 of 18 post-hoc tests; model confound) |

## Correction loop (Exp07, pre-registered)

| loop | n | judge-correct: original → answer | self-labelled correct | precision of the self-label | extra passes (first correction → answer) | repair / harm | billed |
|---|---|---|---|---|---|---|---|
| Codex agent + web search (gpt-6-luna), ≤ 20 passes | 100 | 49% → 62% (Δ +0.13 [+0.02, +0.24], p = 0.035) | 100% | 62% [52, 71] | 61% → 62% (Δ +0.01 [−0.06, +0.08]) | 52% / 20% | $0.18 |
| Claude Code lead + subagents (Haiku), ≤ 20 passes (exploratory, stopped early) | 3 | 0/3 → 2/3 (Luna judge) | 0% (two claims ran 20 passes; one refusal) | – | – | – | $0.03 |

The primary judge is Claude Haiku with the supplied evidence abstracts (93% valid on originals). With Luna as judge (post hoc)
the conclusions are the same: self-label precision 61%, extra passes Δ 0.00.

### Verdict vs correction, single pass vs loop (post hoc, same 100 claims)

Script: [`reports/scripts/compare_verdict_correction.py`](scripts/compare_verdict_correction.py). Details:
[exp07](experiments/exp07_correction_loop.md#post-hoc-comparisons-on-the-same-100-claims-decided-after-exp07-exploratory).

| on the 100 Exp07 claims | no evidence (A / D) | web search (B / C / Codex agent pass 1) | gold abstract (judge) |
|---|---|---|---|
| verdict balanced accuracy | 0.774 / 0.779 | 0.903 / 0.923 / 0.921 | 0.934 |

| correction (Haiku judge) | original | single agent pass | full loop |
|---|---|---|---|
| texts correct | 49% | **62%** (+0.13, p = 0.035) | 62% (+0.00 [−0.06, +0.06] vs single pass) |
| cost / time per claim | – | $0.023 / 34 s | $0.059 / 100 s |

The agent detects 93% of false claims but repairs only about half of them. Looping had the same observed
correctness as one pass (Δ CI [−0.06,+0.06]), at 2.5× the estimated notional cost.

## Error-injection benchmark (Exp08, pre-registered)

The benchmark is 20 AI-research passages (Wikipedia leads and arXiv abstracts) with 48 annotated edits and 4
no-injection controls. The corrector is a Codex agent (`gpt-6-luna`) with web search, forced to make 4 passes. The primary judge
is `claude-haiku-5-5`, which scores each text against the original passage.

| prompt | score: corrupted → pass 1 → pass 4 | weighted fix score, pass 1 → 4 | pass 4 − pass 1 [95% CI] | words, pass 4 (original 157) | time / pass | billed estimate |
|---|---|---|---|---|---|---|
| naive ("Fact-check the following text.") | 38.6 → **90.4** → 89.4 | 0.958 → 0.969 | −1.0 [−6.8, +5.3] | 191 | 18 s | $0.07 |
| rigorous (full default prompt) | 40.0 → **85.7** → 86.2 | 0.969 → **0.896** | +0.45 [−4.6, +4.8] | 254 | 110 s | $0.09 |

Details: [exp08](experiments/exp08_ai_error_bench.md).

## Qualitative runs (Exp00)

Nine runs covered presets L0–L5, iteration, Claude/Codex agents and subagents. They made 49 calls in total. The eight
runs on the keyed texts agreed with the answer key on all 42 claim verdicts; the ninth used a 2-claim test text
(details and costs: [exp00](experiments/exp00_ai_texts.md)).

## What was learned across experiments

- **Search-enabled configurations improved verdicts in this SciFact sample.** Larger gains occurred on CONTRADICT
  claims (recall 0.72 → 0.88–0.93; SUPPORT 0.79 → 0.85). The data do not establish the model's internal reasons.
- **The rigorous prompt generated more output.** It used 8.5× the output tokens with no detected verdict gain
  over the minimal search prompt. This evaluation does not measure the usefulness of labels, conditions or issue lists.
- **Exp00's L5 run gave more moderate scores.** The single observed run does not isolate synthesis as the cause.
- **Self-assessed stopping is not verification** (Exp07). The loop marks everything correct, 76% of items after
  1–2 passes and the rest within 8. 38% of those texts are wrong by gold evidence, and further passes rewrite rather
  than repair (hedging, question drift).
- **No extra gain detected beyond one pass** (post hoc, Exp07). A single agent pass with web search has the same
  observed correctness as the loop (Δ 0.00, CI [−0.06,+0.06]); the loop costs 2.5× more in estimated notional usage.
- **Iteration erodes annotated specifics** (Exp08). One pass fully corrects 44/48 or 45/48 annotated edits. Further passes with
  the rigorous prompt never change a fully corrected annotation to uncorrected in the stored judgments, but they hedge or drop restored
  facts (45 → 38 fully corrected) while the self-rating stays at 96%.
- **Reference-based judging needs validation** (Exp08, post hoc). Some flagged additions are supported; others
  are source conflicts (Transformer 41.0 vs 41.8 BLEU, AlexNet 500,000 vs 650,000 neurons) or unresolved claims.
- **Verdict scores exceeded correction scores in Exp07's setting.** The checker reached about 0.92 balanced
  accuracy on original claims and the evidence judge reached 0.93, while that judge accepted 62% of returned
  corrections. These metrics use different targets and denominators and do not establish general task difficulty.
- **Ranking and threshold can disagree.** The Claude agent ranked well (AUROC 0.962) but had a poor 50% cut-off
  (Exp05).
  The prompt without search raised AUROC without raising accuracy (Exp03). The threshold metric alone hides this.
- **Delegation can be fabricated.** In 4 smoke tests Codex never spawned a sub-agent, and twice it claimed one had
  answered (Exp00).
- **Refusals are a failure mode of their own.** Anthropic's bio-safety filter refused some biomedical claims,
  non-deterministically, and the JSON repair step turned refusals into fabricated verdicts on two claims (fixed,
  Exp05).
- **Engineering findings** (Exp00): workspace header, direct search mode, CLAUDE.md isolation, Codex AGENTS.md
  limitation, the subagent-delegation prompt. See the table in [exp00](experiments/exp00_ai_texts.md).

## Spend

The local `logs/spend.jsonl` contains 2,953 entries and **$7.34726649 in known billed estimates** as checked on
2026-10-22. One billed entry has unknown cost. This is not a provider-invoice total; subscription fees and
unrecorded usage are excluded. The $10 setting is a soft recorded-cost control. Raw logs and runs are ignored
by Git; committed summaries and per-item predictions support only the analyses described in the
[verification record](verification_2026-10-22.md).
