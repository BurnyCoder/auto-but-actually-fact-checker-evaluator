# Subagent and per-claim combinations: verification, 2026-10-28

**Problem reported:** choosing the per-claim / per-scientist agent options raised a "subagents" error pop-up.

**Versions:** Claude Code 2.1.312, Codex CLI 0.165.0, Gradio 6.30.0.

**Auth and models:** agent runs used subscription auth (not billed to the API ledger); API steps used `gpt-6-luna`.

## Cause

`FactCheckConfig._check_combinations` accepted a subagent strategy only with a Claude Code check agent that had
`allow_subagents` ticked. The UI's default check step is an API call, so the "Invalid configuration" pop-up
appeared.

An offline sweep of claim strategy × scientist strategy × check kind × provider × `allow_subagents` covered 72
combinations; 35 were rejected. Codex was excluded because of the Exp00 smoke test, in which Codex never spawned a
subagent.

## Codex spike: `--ephemeral` broke `spawn_agent`

Evidence: [codex_subagent_spike_2026-10-28](results/codex_subagent_spike_2026-10-28/).

The role is declared with `-c agents.echo-agent.description=… -c agents.echo-agent.config_file=echo-agent.toml`. The
lead agent is told to spawn it and repeat its answer. The code word `KUMQUAT-7319` appears only in the role's
`developer_instructions`.

| run | `--ephemeral` | answer | log |
|---|---|---|---|
| `spawn_ok.jsonl` | no | `KUMQUAT-7319` (no shell command run) | no error |
| `spawn_ephemeral_control.jsonl` | yes | "SPAWN FAILED — … no rollout found for thread id …" | `collab spawn failed` |
| `spawn_ephemeral_pineapple.jsonl` | yes | `PINEAPPLE` (guessable from that older role's description) | `collab spawn failed` |

The only difference between the first two runs is the `--ephemeral` flag. This is a causal, single-variable
intervention with n = 1 per arm. It explains the Exp00 result: the spawns failed, and the model invented the
answers. `codex exec --json` emits no spawn item, and its `wait` items list no receivers even when the spawn
worked, so Codex logs cannot show delegation. Only spawn failures are visible.

## Fixes

- **Codex roles:** Codex runs subagent strategies with one named role per `prompts.build_agents` definition
  (`backends/codex.py`). `--ephemeral` is dropped when subagents are allowed.
  `agents.max_concurrent_threads_per_session` is set to the step's `max_subagents`: with the default, 2 of 6
  parallel spawns failed with "agent thread limit reached" (rows c7 and c12 below).
- **Validator:** subagent strategies need only `kind="agent"`; the strategy implies `allow_subagents`.
- **UI:** `config.fix_combination` changes the conflicting setting, never the one just edited, and shows a note.
  - Model ↔ provider.
  - Subagent strategy ↔ API check step.
  - Check step off ↔ nothing to run.
- **Live tests:** `test_codex_subagent_spawn` is new. `test_claude_code_subagent_spawn` now uses the code word,
  because "PINEAPPLE" was guessable from the subagent description.

## Live combination matrix

Input: `The Eiffel Tower is in Berlin. Water boils at 100 degrees Celsius at sea level.`

One run per combination, a 2-claim toy text, model-reported accuracies. This tests that each combination runs
end to end; it says nothing about fact-checking accuracy.

- **Settings:** the check step uses `claude-haiku-5-5` (Claude Code) or `gpt-6-luna` (Codex). Search is off
  unless stated. The subagent-per-scientist runs use 2 scientists (Popper, Feynman).
- **Columns:** "spawns" counts Claude Code `Agent`/`Task` tool calls. For Codex, only spawn failures are
  observable.
- **Evidence:** per-run counts are in [subagent_matrix_2026-10-28.json](results/subagent_matrix_2026-10-28.json),
  produced by [summarize_subagent_matrix.py](scripts/summarize_subagent_matrix.py).

| # | claims | scientists | check | status | calls / errors | spawns | Codex spawn failures | accuracy (Eiffel, boiling) |
|---|---|---|---|---|---|---|---|---|
| c1 | subagent | none | Claude Code | done | 1 / 0 | 2 | – | 0, 70 |
| c2 | whole text | subagent | Claude Code | done | 1 / 0 | 2 | – | 1, 90 |
| c3 | subagent | subagent | Claude Code, search (preset L3) | done | 1 / 0 | 6 | – | 0, 75 |
| c4 | separate call | subagent | Claude Code | done | 4 / 0 | 5 | – | 0, 90 |
| c5 | subagent | none | Codex | done | 1 / 0 | n/a | 0 | 0, 98 |
| c6 | whole text | subagent | Codex | done | 1 / 0 | n/a | 0 | 0, 85 |
| c7 | subagent | subagent | Codex | done | 1 / 0 | n/a | **3** | 0, 97 |
| c8 | separate call | subagent | Codex | done | 4 / 0 | n/a | 0 | 0, 90 |
| c9 | separate call | none | Codex, search (preset L4) | done | 4 / 0 | – | 0 | 0, 99 |
| c10 | separate call | separate call | API (preset L5, search off) | done | 12 / 0 | – | – | 0, 90 |
| c11 | separate call | none | API | done | 4 / 0 | – | – | 0, 90 |
| c12 | subagent | subagent | Codex, search (L3 on Codex) | done | 1 / 0 | n/a | **2** | 0, 95 |
| c7b | c7 after the thread-cap fix (`max_subagents=6`) | | Codex | done | 1 / 0 | n/a | 0 | 0, 90 |
| c12b | c12 after the thread-cap fix | | Codex, search | done | 1 / 0 | n/a | 0 | 0, 95 |

**Observations:**
- Every combination finished with a parsed JSON summary.
- The Eiffel claim was scored 0–1 % in every run.
- The boiling-point claim ranged from 70 % to 99 %. Its precision caveat (pressure, ITS-90 ≈ 99.97 °C) is
  judged differently across backends and runs.
- With n = 1 per combination, differences between rows are not evidence of a strategy effect.

**Spend:** the whole matrix cost $0.042 billed: the ledger went from $7.5087 to $7.5509 (API extract, synthesis
and per-claim calls). Agent runs were subscription runs; their CLI or catalog estimates are notional.

## UI check (preview pane, Gradio 6.30)

Each edit below showed one note and no "Invalid configuration" pop-up:

| edit | automatic change |
|---|---|
| "one subagent per claim" with the default check step | check step became an agent (Codex) |
| `claude-haiku-5-5` on the OpenAI check step | provider became anthropic |
| "one subagent per scientist" with the API check step | Claude Code agent |
| check step back to `api` | strategies became the separate-call ones |
| Check step unticked, then scientists "none" | Check step switched back on |

The model dropdown's `.input` fired twice per pick, which showed duplicate notes, so it uses `.select` instead.

## Limitations

- Codex delegation in the matrix runs is inferred, not observed: there were no spawn failures and the lead
  agent's own messages ("will have each checked independently"). The mechanism itself is verified by the code-word
  test.
- `codex exec --json` usage may not include subagent threads. Codex cost estimates for subagent runs may be low.
- One run per combination; no repetition across seeds or texts.
