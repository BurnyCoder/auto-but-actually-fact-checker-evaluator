# Exp07 pre-registration — is text that the correction loop labels "correct" actually correct?

Written and committed **before** any Exp07 agent or judge call. Results go to
`reports/experiments/exp07_correction_loop.md`. Anything decided after seeing data is marked *post hoc*.

## Why

The iterate-until-accurate loop has only been shown to *converge*. Exp00 went 18% → 95%; a UI run went 50% →
98% → 99%. In every case the scores came from the same model that wrote the corrections, which measures
self-consistency, not truth. Exp01–05 scored verdicts on original claims, never the quality of corrections. The
loop has also never been run by an agent.

## Data

- **Claims:** the first 100 claims of the Exp01 sample (`reports/results/exp01/items.json`, seed 0): 54 SUPPORT
  (true) and 46 CONTRADICT (false).
- **Optional arm:** the first 40 of the same claims (also used in Exp04/05).
- **Gold evidence:** for each claim, the cited SciFact abstract(s) from the corpus parquet, with the expert
  rationale sentences marked (Wadden et al. 2020).

## Systems (loops under test)

**Primary:** [`configs/bench/loop_codex_search.json`](../configs/bench/loop_codex_search.json).
- A Codex agent (`gpt-6-luna`, effort low, live web search) with the full default prompt.
- The search cap (3) and the blocked dataset hosts are stated in the prompt.
- It iterates while it rates some claim below 90% accuracy, for at most **20 passes**, and stops at a fixed point
  (corrected text unchanged).

**Optional:** [`configs/bench/loop_claude_subagents.json`](../configs/bench/loop_claude_subagents.json).
- A Claude Code lead agent (`claude-haiku-5-5`) with web search.
- It runs one claim-checker subagent per claim, plus one scientist-perspective subagent per claim × scientist
  (Popper, Feynman, Gelman), with at most 6 subagents.
- Same iteration rule as the primary loop.

**The loop's answer.** If the loop stops because it rates every claim ≥ 90%, the text it rated is what it
*labels correct* (the input of its last pass). Otherwise its answer is its latest corrected text, which is not
self-labelled.

## Judge

**Inputs:**
- the gold abstract (rationale sentences marked)
- the original claim, which fixes the question
- the text to judge

The judge uses no web and no outside knowledge.

**Output:** JSON with three decision fields (plus a `verdict` and an `explanation`).
- `main_claim_entailed`: the central assertion is supported by the gold evidence.
- `contradicts_evidence`: some statement in the text conflicts with the gold evidence.
- `same_question`: the text is still a specific claim about the same question. This blocks vacuous
  "corrections".

**Correct** = entailed ∧ ¬contradicts ∧ same_question. A missing or refused verdict counts as **missing**, not
wrong.

**Primary judge** = the other model family from the corrector:
- Codex/Luna loop → `claude-haiku-5-5` judge
- Claude/Haiku loop → `gpt-6-luna` judge

**Secondary judge** = the other model. It is reported for agreement (Cohen's κ).

**Judge validity, checked before any hypothesis:**
- On the 100 original claims, a valid judge calls SUPPORT claims correct and CONTRADICT claims incorrect.
- Its accuracy against gold is reported.
- If the primary judge's accuracy is below 85%, Exp07's conclusions are flagged as unreliable (checked from the
  analysis output; the script reports the accuracy but does not apply the gate).

## Hypotheses and analysis

All of these use the primary judge, items with non-missing verdicts, and
[`reports/scripts/analyze_correction.py`](../reports/scripts/analyze_correction.py).

- **H1 (primary): the loop increases correctness.**
  - The share of texts judged correct rises from the original claim to the loop's answer.
  - Test: paired exact McNemar, α = 0.05. Δ is reported with a paired-bootstrap 95% CI (10,000 resamples,
    seed 0).
  - Falsified if Δ ≤ 0 or its CI includes 0.
- **H2 (key descriptive): how precise is the self-label?** P(judge-correct | the loop self-labelled the text
  correct), with a Wilson 95% CI. This is the direct answer to "is 'labelled correct' actually correct?".
- **H3 (secondary): does looping beyond the first correction help?** Compare the first pass's corrected text with
  the loop's answer (paired McNemar).
- **Descriptive:**
  - repair rate: CONTRADICT originals whose answer is correct
  - harm rate: originals judged correct whose answer is judged incorrect
  - passes distribution, share hitting 20 passes or a fixed point, stop reasons
  - judge-correct share and self-assessed accuracy per pass, with items carried forward after they stop
  - cost (billed and notional), refusals, leak flags
- **Optional arm:** the same analysis, labelled exploratory (n = 40, different model family).

## Power and budget

- **Power:** about half the originals are false. A loop that repairs most of them while rarely harming true claims
  gives a discordant fraction of roughly 0.3–0.4. With n = 100, a 25-point rise has power well above 80% (Connor
  1987). Smaller effects, the optional arm (n = 40) and H3 are exploratory.
- **Budget:** agents run on subscription logins, so $0 is billed for them. Judges cost about $0.0003–0.0005 per
  call; the expected total is ≈ $0.5. All of it stays inside the project's $10 cap, which had $3.33 left before
  Exp07.

## Threats to validity

- **Gold evidence is one abstract.** A correction that is right according to newer or broader literature can be
  judged "not entailed". That makes the judge conservative and biases H1 *against* the loop.
- **The judge is an LLM.** Its validity is measured on the originals, and cross-family judging avoids a model
  grading its own family. Disagreement between the two judges is reported.
- **Leakage.** The corrector may find the SciFact paper itself. That is legitimate evidence, but the dataset
  hosts are blocked and flagged.
- **Pretraining contamination** may make corrections easier for both arms.
