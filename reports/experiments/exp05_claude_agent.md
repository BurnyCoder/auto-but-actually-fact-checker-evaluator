# Exp05 — Full rigorous prompt run by a Claude Code agent (post hoc, small)

**Status:** post hoc, exploratory, underpowered (n = 40). It closes the plan's gap of benchmarking a Claude Code
agent as well as Codex. **Data:** `reports/results/exp05_claude_agent/`. **System F:**
[`configs/bench/full_agent_claude.json`](../../configs/bench/full_agent_claude.json). **Date:** 2026-10-17.

## Setup

- **Runner:** `claude -p` with `claude-haiku-5-5`, effort low, WebSearch/WebFetch allowed, and the full default
  prompt.
- **Search limits:** the cap of 3 searches and the blocked hosts are stated in the prompt; agents have no
  API-level filter.
- **Auth:** subscription, so $0 billed ($1.27 notional, $0.032 per claim).
- **Items:** the same 40 claims as Exp04 (the first 40 of the Exp01 sample; 23 SUPPORT, 17 CONTRADICT).

**Confound:** F differs from every other system in the **model** (Haiku vs Luna) as well as in being a Claude
Code agent, so no comparison isolates "agent vs API call".

## Results (paired on the same 40 items)

| system | balanced accuracy on these 40 | F − system [95% paired bootstrap CI] | McNemar b / c, p (b = only the row's system right, c = only F right) | Δ AUROC (F − system) [95% CI] |
|---|---|---|---|---|
| F Claude Code agent (Haiku) | 0.797 | – | – | – |
| A minimal, no search (Luna) | 0.825 | −0.028 [−0.177, +0.123] | 6 / 4, 0.75 | +0.073 [−0.033, +0.217] |
| B full + API search (Luna) | 0.905 | −0.109 [−0.241, +0.024] | 7 / 2, 0.18 | −0.017 [−0.075, +0.027] |
| C minimal + API search (Luna) | 0.935 | −0.138 [−0.250, −0.045] | 6 / 0, 0.031 | −0.031 [−0.091, +0.001] |
| E Codex agent (Luna) | 0.876 | −0.079 [−0.225, +0.066] | 7 / 3, 0.34 | +0.045 [−0.042, +0.163] |

F's own metrics:
- accuracy 0.775 [Wilson 0.625, 0.877]
- AUROC 0.962 on these 40 claims: above A (0.889), D (0.934) and E (0.917), below B (0.978) and C (0.992) on the
  same claims; Brier 0.161
- SUPPORT recall **0.65**, CONTRADICT recall 0.94; median score 55 for SUPPORT vs 9 for CONTRADICT
- 2.05 searches per claim
- about 11.4k output tokens per claim (agent turns included); median 55 s per claim
- 1 refusal, 1 leak flag

## Interpretation

- **It ranks well but is sceptical.** The Haiku agent orders claims well (AUROC 0.962, though B and C rank the same
  40 claims better) but puts true claims low: 8 of 23 SUPPORT claims scored below 50. The pre-registered 50% threshold therefore costs it
  accuracy. A threshold tuned on held-out data would likely help. That was not done, since it would be tuning on
  the evaluation set.
- **F is worse than C here**, the only nominally significant comparison (−0.138, p = 0.031). It is 1 of 9
  post-hoc comparisons (18 post-hoc tests counting Δ AUROC) and confounded by the model, so it is not a finding.
- **Refusals.** Two biomedical claims triggered Anthropic's bio-safety refusal ("Haiku 5.5 can't help with this").
  - On a re-run, one succeeded (correctly) and one was refused again. It is scored wrong under the
    pre-registered rule.
  - Refusals are **non-deterministic** and specific to the provider and domain, which matters for biomedical
    fact-checking with Anthropic models.
- **The leak flag is benign.** The agent opened `physics.paperswithcode.com/author/…`, an author page and not a
  dataset page. This shows that prompt-level domain blocking for agents is not enforced.

## Bugs found and fixed by this run

| issue | fix |
|---|---|
| A Claude Code refusal came back as `is_error` with subtype "success", logged unhelpfully as `errors=['success']` | the error now carries the stop reason and message (`refusal: API Error: …`) |
| **The JSON repair step "repaired" the refusal message into a fabricated verdict** (p_true 1.0 and 0.5 on two refused claims) | repair is skipped when the call itself failed (`summarize_output(failed=True)`), with a regression test |
| refused items were retried forever as transient failures | the benchmark caches refusals as final (no verdict, scored wrong) |
