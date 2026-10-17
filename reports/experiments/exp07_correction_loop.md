# Exp07 — Is text that the correction loop labels "correct" actually correct?

**Pre-registration:** [`docs/correction_eval.md`](../../docs/correction_eval.md). It was committed (PR #14) before
any Exp07 call, together with the analysis script
[`reports/scripts/analyze_correction.py`](../scripts/analyze_correction.py).
**Data:**
- `reports/results/exp07_correction_codex/`
- `reports/results/exp07_correction_claude/`
- analysis: `reports/results/correction_analysis.json`
- post-hoc judge swap: `correction_analysis_luna_judge_posthoc.json`

**Date:** 2026-10-17.

## Question

Exp00 and the UI runs showed the iterate-until-accurate loop *converges* (e.g. 18% → 95%). But the scores came
from the same model that wrote the corrections. Is the text the loop finally labels correct actually correct
according to independent, gold evidence?

## Method (as pre-registered)

- **Items:** the first 100 Exp01 SciFact claims: 54 true (SUPPORT), 46 false (CONTRADICT).
- **Primary loop:** a Codex agent with live web search.
  - `gpt-6-luna`, effort low, the full default prompt.
  - The search cap and blocked hosts are stated in the prompt.
  - It repeats correct → re-check until it rates every claim ≥ 90%, for at most 20 passes, with a fixed-point stop.
  - The loop's answer is the text it labels correct: the input of its last pass.
- **Judge:**
  - Input: the cited SciFact abstract with the expert rationale sentences marked, plus the original claim (which
    fixes the question). No web.
  - Output: correct = central claim entailed ∧ no contradiction ∧ still a specific claim on the same question.
  - Primary judge: `claude-haiku-5-5`, a different model family from the corrector. Secondary judge: `gpt-6-luna`.

## Results — Codex loop (n = 100)

**Judge validity (gate: ≥ 85% on originals, where truth is known)**
- Haiku: **93%** [86, 97], gate passed.
- Luna: 83% [74, 89], below the gate; it is used only as the secondary judge.
- The judges agree on 73% of 331 judged texts, Cohen's κ = 0.47 (moderate).

| measure (primary judge) | result |
|---|---|
| **H1** share correct: original → loop answer | **49% → 62%**, Δ = **+0.13 [+0.02, +0.24]**, McNemar 10 / 23, p = 0.035 → **supported** |
| **H2** precision of "labelled correct" | the loop labelled **100/100** answers correct (all stopped on "all claims ≥ 90%"); judged correct: **62%** [52, 71] |
| **H3** first correction → final answer | 61% → 62%, Δ = +0.01 [−0.06, +0.08], McNemar 5 / 6, p = 1.0 → **extra passes add nothing** |
| repair rate (false originals now correct) | 24 / 46 = **52%** [38, 66] |
| harm rate (correct originals now incorrect) | 10 / 49 = **20%** [11, 34] |
| answer correct, by gold class | true claims 38 / 54 = 70%; false claims 24 / 46 = 52% |
| passes | 1 pass: 10, 2: 66, 3: 15, 4: 5, 5: 1, 6: 2, 8: 1 (none reached 20, none stopped on a fixed point) |
| cost | $0.18 billed (judges and JSON repair); $6.04 notional for the Codex agent (subscription); 456 searches; 0 leak flags |

**Robustness** (post hoc, Luna as judge):
- H1 Δ = +0.24 [+0.13, +0.35]; Luna rates fewer originals correct (37%), hence the larger gain.
- H2 precision 61% [51, 70].
- H3 Δ = 0.00 [−0.06, +0.06].
- Repair 57%, harm 19%.

The conclusions hold under either judge.

**Trajectory** ([`fig3_correction_loop.png`](../figures/fig3_correction_loop.png); the latest proposed correction,
carried forward after an item stops):
- The loop's own rating of the text it checks jumps from 0.45 to about 0.93 after the first pass and stays at
  0.91–0.95.
- Gold-evidence correctness rises from 0.49 to 0.61 after the first correction, then *drifts down* to about 0.50
  as further rewrites are proposed.

## Interpretation

1. **The loop helps, but much less than it claims.** It turns 49% correct into 62% correct (H1), mostly by fixing
   crisp factual errors. Example: "ComYMV genome consists of 2140 base pairs" → "7,489 base pairs", confirmed by
   both judges.
2. **"Labelled correct" is a weak signal.** Every one of the 100 answers was self-labelled ≥ 90% accurate, but only
   62% are correct by the gold evidence. The self-label is unconditional, so it carries no information about which
   answers are right.
3. **Looping beyond the first correction does not help** (H3 null). The extra passes mostly rewrite rather than
   repair. Clinical and causal claims drift into hedged or narrower statements, e.g. "Having a main partner worsens
   HIV outcomes" ended after 6 passes as a description of one 2021 survey. The loop's own score climbs (18 → 95)
   because a hedged statement is hard to dispute, while it stops answering the original question.
4. **The loop also harms, because the checker is sceptical of true claims.**
   - 1 in 5 originally correct texts was made incorrect.
   - All 10 harmed items are true claims that pass 1 wrongly scored 35–80%.
   - Pass 1 rated **44 of the 54 true claims below 90%** and sent them to be rewritten. Only 10 true claims were
     left untouched; they stopped after 1 pass and their output equals the (correct) original.
   - Rewriting a true claim mostly hedges it or changes the question.

## Results — Claude Code subagent loop (optional arm)

**Status:** exploratory, n = 3.

**What happened to the arm.** It was stopped by user decision after the in-flight claims finished, because it did
not converge:
- After 20 minutes both in-flight loops were at pass 7–8, with self-ratings drifting *down* (75 → 55).
- At about 2.5–4 min and about 1M input tokens per pass, 40 claims × 20 passes would have taken roughly 20 hours.

**Deviation.** The stop watcher counted cached records, not the two specific claims.
- When train-815 finished, the free worker picked up a third claim, train-853. It was refused at once and cached,
  which tripped the watcher.
- The watcher then interrupted the second in-flight claim, train-278. Its loop had already completed all 20 passes;
  only its judging was cut off.
- That judging was re-done from the saved `runs/<id>/run.json` with the same functions and judges. The record is
  marked `recovered`.

| claim (gold) | passes | self-rating per pass | stop | loop answer judged correct (Luna / Haiku) | all produced texts judged correct (Luna / Haiku) | notional cost |
|---|---|---|---|---|---|---|
| train-278 ComYMV "2140 bp" (false) | 20 | 5, 85, then 50–75 | none (limit reached, never self-labelled) | ✓ / ✓ | 17 / 21, 6 / 21 | $2.41 |
| train-815 RIM1 → IME1 RNA (true) | 20 | 60, 35, then 55–75 | none (limit reached, never self-labelled) | ✓ / ✓ | 16 / 21, 20 / 21 | $2.27 |
| train-853 primates / EILV (false) | 1 | – (Haiku bio-safety refusal) | no parseable summary | ✗ / ✗ (original kept) | – | $0.02 |

**Reading.**
- The sceptical multi-agent checker **never** labelled anything correct, in 40 passes over two claims. It kept
  rewriting texts that the judges mostly consider correct, so its self-rating was unrelated to correctness.
- This is the mirror image of the Codex loop, which labels everything correct too early.
- Neither loop's stopping signal tracks truth.
- The two judges disagree sharply on these long, multi-sentence rewrites (κ = 0.11 across 43 texts).
- The arm's primary judge (Luna, cross-family) misjudged the true original (validity 2/3).
- Cost: $0.03 billed (judges), $4.70 notional, 174 searches.

## Limitations

- **The gold evidence is one abstract.** A correction that is right according to broader literature can be judged
  "not entailed", which biases correctness *against* the loop. The H2 precision is therefore a lower bound in that
  respect.
- **The judges are LLMs.** Haiku is 93% accurate on originals; Luna is 83%; they agree moderately (κ 0.47).
  Hedged texts are where they disagree most.
- **One corrector model** (`gpt-6-luna`, effort low) **and one domain** (biomedical single-sentence claims).
- **H1's effect is modest** and its CI lower bound (+0.02) is close to 0.

## Learnings

- A self-assessed stopping rule (`iterate_until_accurate`) measures how persuaded the model is by its own
  correction, not correctness. Use at most one correction pass, or an independent check, before calling a text
  "verified".
- The pre-registered `same_question` criterion was necessary: without it, hedged non-answers would have counted as
  correct.
