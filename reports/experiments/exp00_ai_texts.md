# Exp00 — End-to-end runs of every preset on AI-research, AI-philosophy and AI-engineering texts

**Type:** functional / qualitative validation. This is not a benchmark: the three texts were written for this
project by the AI coding agent that builds it, and their errors are planted and well known.
**Date:** 2026-10-17 · **Models:** `gpt-6-luna` (OpenAI API and Codex), `claude-haiku-5-5` (Claude Code)
· **Billed cost:** about $0.53 for the runs below, plus about $0.02 for the UI checks.

## Question

Does every execution mode (presets L0–L5, iteration, perspective calls) run end to end through the real APIs and
CLIs, and produce:
- the requested JSON contract: 45 labels and 12 conditions per claim, each with a confidence
- verdicts that agree with an answer key written in advance?

## Setup

- **Texts:** [`examples/`](../../examples). **Answer key:** written before the runs, with sources in
  [`docs/examples.md`](../../docs/examples.md); the binary form is in
  [`examples/answer_key.json`](../../examples/answer_key.json). A key claim is "true" if it should score ≥ 50%.
- **Matching:** case-insensitive keyword. If a run splits a key claim into parts, the least accurate part counts.
- **Scorer:** [`reports/scripts/score_examples.py`](../scripts/score_examples.py).
- **Commands:** `uv run afc check examples/<text>.md --preset <preset>` with default settings. The iteration run
  used `--iterations 2`.

## Results

| preset | text | calls | backends | searches | billed $ | notional $ (subscription) | Σ call durations (s) | agreement with key |
|---|---|---|---|---|---|---|---|---|
| L1 single call + search | research | 1 | openai_api | 2 | 0.0296 | – | 112 | 6/6 |
| L0 single call, no search | philosophy | 1 | openai_api | 0 | 0.0070 | – | 91 | 5/5 |
| L2 Codex agent | engineering | 1 | codex | 1 | – | 0.0180 | 80 | 5/5 |
| L2 Claude Code agent | philosophy | 1 | claude_code | 5 | – | 0.0791 | 132 | 5/5 |
| L4 extract → Codex agent per claim → synthesis | engineering | 9 | codex + openai_api | 10 | 0.0122 | 0.1294 | 337 | 5/5 |
| L3 Claude lead + subagents (first prompt) | research | 1 | claude_code | 4 | – | 0.0673 | 126 | 6/6, but **0 subagents spawned** |
| L3 (revised orchestrator prompt) | 2-claim text | 1 | claude_code | 2 | – | 0.0508 | 90 | 4 subagents spawned |
| L5 extract → per claim × (general + 3 scientists) → syntheses | philosophy | 32 | openai_api | 30 | 0.4185 | – | 1213 | 5/5 |
| L1 + iterate until accurate | engineering | 2 | openai_api | 4 | 0.0563 | – | 193 | 5/5 (pass 1) |

On every run the JSON contract was complete: 45 scored labels and 12 scored conditions per claim, all with
confidence, and zero parse failures. Run artefacts are in `runs/<id>/`; they are gitignored, but the logs show
every prompt and output.

UI checks were done in the in-app browser:
- an L0 run
- **One more iteration**: iteration 2 reached "all claims ≥ 90% accurate"
- a **Karl Popper** perspective button: an independent call with 1 search, $0.013
- **Stop**: "stopped by user"

### Gap-closing checks (second session)

**UI with a mixed per-step setup.** Run `20261017_155456_…`, $0.09 billed, 24 calls. The settings were changed in the
UI widgets in the browser (not loaded from a preset):
- claims: one separate call per claim
- Check step: OpenAI, search off
- Perspective step: provider switched to Anthropic (the model field followed to `claude-haiku-5-5`), search off

What was exercised:
- **Run:** extract, then 2 parallel claim checks, then a synthesis (iteration 1: 50%).
- **One more iteration**, pressed twice: iteration 2 re-extracted 5 claims from the corrected text (98%);
  iteration 3 reached 99%.
- **Mid-run click:** a click on *One more iteration* during iteration 3 started no second batch; the
  "still in progress" guard was hit.
- **Two scientist buttons** (Popper, Feynman) ran as concurrent independent Haiku calls.
- **Synthesize perspectives:** one Luna call.
- **Run all selected scientists:** three concurrent Haiku calls.

All of these behaved as designed.

**Codex multi-agent smoke test (negative result).**
- **Setup:** Codex 0.163.0, `gpt-6-luna`, `--enable multi_agent` (and in one run also `multi_agent_v2`). Four
  prompts of increasing explicitness asked it to spawn one sub-agent; the last ones named
  `collaboration.spawn_agent`.
- **What happened:** Codex listed its sub-agent tools (`collaboration.spawn_agent`, `wait_agent`, …) but never
  spawned one. Every run emitted only a `wait` collab call with no receivers and empty agent state.
- **Fabrication:** twice the model then answered "SUBAGENT SAID: PINEAPPLE", a fabricated delegation.
- **Evidence:** `reports/results/codex_multiagent_smoke/out*.jsonl`.
- **Consequence:** the subagent strategies stay Claude Code-only. A Codex step's `allow_subagents` only switches
  the feature on, and spawning was not observed with Luna.
- **Update 2026-10-28 (cause found; the result above is kept as recorded):** these spawns failed because the
  backend ran Codex with `--ephemeral`. On Codex 0.165.0 with Luna, an ephemeral session logs
  `collab spawn failed: ... no rollout found for thread id`. The same prompt without `--ephemeral` returned a code
  word that exists only in the subagent's instructions. The same prompt with `--ephemeral` answered "SPAWN
  FAILED" with that error. Codex now runs subagent strategies with named roles; see the
  [subagent verification record](../verification_2026-10-28_subagents.md).

## Observations and learnings

1. **All presets agree with the key on all 42 claim verdicts** (the 8 runs on the keyed texts; the 9th run used a
   2-claim test text). Re-scored on 2026-10-22 with `score_examples.py` from `runs/`. This shows the plumbing works
   and that `gpt-6-luna` / `claude-haiku-5-5` catch these textbook errors. The key's claims are well known and in
   pretraining data, so this is **not** evidence of accuracy on harder material (see Exp01–Exp04 for a
   quantitative test).
2. **Iteration converges in one correction.** The engineering text went from overall accuracy 18% to 95% in
   pass 2, and the loop stopped at the 90% threshold. Caveat: the same model grades its own corrections, so this
   measures self-consistency, not ground truth.
3. **Synthesizing many perspectives moderates scores.** In L5, the final per-claim scores after merging three
   scientist perspectives with the general check were less extreme than in single-call runs:
   - Turing-test claim: 46% (L5) vs 25% (L0) and 5% (L2 Claude)
   - Chinese Room claim: 40% vs 38% / 8%

   They are still below 50%, but closer to the threshold. Averaging-like synthesis trades decisiveness for hedging.
4. **Cost scales with calls × searches.** L5 (32 calls, 30 searches, philosophy text) cost 14× the L1 run (1 call,
   research text), with full agreement in both. Searches at $0.01 each dominate the Luna cost.
5. **Subagent orchestration needed a stronger prompt.** With the first orchestrator wording ("You can delegate…"),
   the Haiku lead agent never called the subagent tool (`subagent_stats.spawned = 0`). The tool is listed as
   `Task` in Claude Code 2.1.302's init event, while the prompt said "Agent" (the docs say the Task tool was
   renamed Agent in 2.1.63 and `Task` remains an alias: https://code.claude.com/docs/en/sub-agents). After making
   delegation mandatory and naming the tool and `subagent_type`, it spawned 4 subagents (2 claim-checkers + 2 scientist perspectives).
   Fix: commit `3909f01`.

## Bugs found and fixed during these runs

| issue | how it was found | fix |
|---|---|---|
| Anthropic API returned 400: key not scoped to a workspace | live test | send `anthropic-workspace-id` from `.env` (`ANTHROPIC_WORKSPACE_ID`) |
| Haiku web search used up `max_uses` through "dynamic filtering" code execution and answered from memory | live test (0 searches recorded) | `allowed_callers: ["direct"]`; verified with 1 search and citations |
| Claude Code agents still loaded the user's `~/.claude/CLAUDE.md` despite `--setting-sources project` | canary prompt answered YES | `--settings` with `claudeMdExcludes` + `autoMemoryEnabled: false` → canary NO |
| Codex agents load `~/.codex/AGENTS.md`, and no config key disables it | canary YES; [config reference](https://learn.chatgpt.com/docs/config-file/config-reference) | api_key mode: empty `CODEX_HOME` (canary NO); subscription mode: `developer_instructions` note (limitation documented) |
| `afc bench --systems …` rejected | first pilot attempt | `parse_known_args` passthrough plus a CLI test |
| per-claim syntheses ran sequentially (about 3 min idle in L5) | L5 call timestamps | `parallel_map` over the syntheses |
| labels that don't apply came back as "fully" with 0% | inspection of the first real output | contract now asks for `degree: null` when a label does not apply |
