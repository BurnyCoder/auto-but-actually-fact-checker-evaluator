# Exp04 — Full rigorous prompt run by a Codex agent (post hoc, small)

**Status:** post hoc, exploratory and underpowered (n = 40). **Data:** `reports/results/exp04_codex_agent/`.
**System E:** [`configs/bench/full_agent_codex.json`](../../configs/bench/full_agent_codex.json). **Date:** 2026-10-17.

## Why

The product's main promise is agentic fact-checking (Codex / Claude Code with live web search). E runs the same
full rigorous prompt as B, but through `codex exec`:
- `gpt-6-luna`, effort low, `web_search="live"`
- the search cap of 3 and the blocked hosts are stated in the prompt, because agents have no API-level filter
- the user's ChatGPT subscription (not billed; notional API-price cost $0.91, i.e. $0.023 per claim)

The 40 items are the first 40 of the Exp01 sample: 23 SUPPORT and 17 CONTRADICT.

## Results (paired on the same 40 items)

| system | balanced accuracy on these 40 | E − system [95% paired bootstrap CI] | McNemar b / c, p (b = only the row's system right, c = only E right) | Δ AUROC (E − system) [95% CI] |
|---|---|---|---|---|
| E Codex agent, full prompt | 0.876 (Wilson accuracy CI [0.739, 0.945]) | – | – | – |
| A minimal, no search | 0.825 | +0.051 [−0.073, +0.177] | 2 / 4, 0.69 | +0.028 [−0.041, +0.108] |
| B full prompt + API search | 0.905 | −0.029 [−0.124, +0.048] | 2 / 1, 1.0 | −0.061 [−0.172, +0.003] |
| C minimal + API search | 0.935 | −0.059 [−0.167, +0.034] | 3 / 1, 0.62 | −0.075 [−0.191, −0.001] |

E's own metrics:
- AUROC 0.917, Brier 0.113
- 1.8 searches per claim on average (vs 1.17 for B through the API)
- no parse failures, no leak flags
- median call duration 34 s

## Interpretation

- **At n = 40 the agent is statistically indistinguishable from the single API calls.** Every balanced-accuracy
  CI spans about ±10 pp. The AUROC CI against C just excludes 0, but that is 1 of 18 post-hoc tests (9 comparisons
  × Δ balanced accuracy and Δ AUROC) and is
  not interpreted.
- **This is not evidence that agents are useless for fact-checking.** The task (one atomic biomedical claim, one
  search usually enough) rewards one targeted search. Agents' advantages (multi-step research, reading full
  pages, following references) are not exercised.
- **Cost:** $0.023 notional per claim, vs $0.015 for B, with more searches.

## Learnings

- Under subscription auth, agent runs cost $0 in API billing but are rate-limited. Four parallel Codex runs
  worked without throttling here.
- A Codex agent also loads the user's global `~/.codex/AGENTS.md` in subscription mode; it was neutralised only
  by a developer-instruction note. A cleaner agent comparison should use `AGENT_AUTH=api_key`, where `CODEX_HOME`
  is an empty temporary directory.
