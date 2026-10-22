# Architecture

This page describes how the modules fit together. The overview graph is in the [README](../README.md#architecture).

## Modules and responsibilities

| module | responsibility |
|---|---|
| `config.py` | `.env` `Settings`; `StepConfig` (per step); `FactCheckConfig` (whole run); presets; dotted overrides; `active_conditions()` |
| `catalog.py` | model price table (verified 2026-10-17, re-checked 2026-10-22), `cost_usd()` including long-context tiers (input, cached input, output) and $0.01/search |
| `spend.py` | append-only `logs/spend.jsonl`, soft pre-call `check_budget()` against recorded billed cost estimates |
| `logs.py` | one timestamped log file per process plus the terminal; `log_block()` for full prompts/outputs; per-run log handlers filtered by `run_id` |
| `prompts.py` | Jinja2 rendering of `prompts/`: `sections_text`, `output_contract`, `build_prompt(cfg, step, text, …)`, `build_agents(cfg)` |
| `schema.py` | the JSON output contract (`FactCheckSummary`, `ClaimVerdict`, `LabelScore`, `Assessment`, `ClaimType`, `ClaimList`), the benchmark judge and injection models (`JudgeVerdict`, `InjectedError`/`InjectionList`, `RefError`/`RefVerdict`) and `parse_block()` |
| `results.py` | `CheckResult`, `IterationResult`, `FactCheckRun` (+ `current_text`), `CallRecord`, in-memory `RUNS`, `runs/<id>/run.json` |
| `context.py` | `RunContext.call()`: the single LLM choke point; `stop_run()` |
| `phases/` | `extract_claims`, `check` (+ `summarize_output` → repair), `synthesize` (LLM or deterministic merge), `should_stop` |
| `pipeline.py` | `run_fact_check` → `run_iteration`; `run_perspective`; `synthesize_perspectives`; `parallel_map` |
| `backends/` | `openai_api`, `anthropic_api`, `claude_code`, `codex`, shared `subprocess_jsonl` |
| `render.py` | Markdown report and table rows shared by the UI and the CLI |
| `ui.py` | Gradio Blocks: StepConfig widgets generated from the fields, FactCheckConfig fields listed per tab |
| `bench/` | `datasets` (SciFact), `metrics`, `run` (`afc bench`), `correction` + `judge` (`afc correct-eval`, Exp07), `ai_errors` + `sources` + `judge` (`afc ai-errors`, Exp08) |

## Call graph of one iteration

```mermaid
sequenceDiagram
  participant P as pipeline.run_iteration
  participant E as extract
  participant C as check / perspective
  participant S as synthesize
  participant X as RunContext.call
  P->>E: claim_strategy == separate_call_per_claim
  E->>X: extract prompt
  P->>C: parallel_map over (target × [general check] + perspective scientists)
  C->>X: check prompt (+ --agents for subagent strategies)
  C->>X: repair prompt (only if the JSON summary is missing, repair is on and the call did not fail)
  P->>S: per target (when >1 result), then the whole text (when >1 target)
  S->>X: merge prompt (+ repair prompt under the same rule)
```

## How the backends map the settings

| StepConfig field | OpenAI Responses | Anthropic Messages | Claude Code | Codex |
|---|---|---|---|---|
| `effort` | `reasoning.effort` | `output_config.effort` (none/minimal → low) | `--effort` (none/minimal → low) | `-c model_reasoning_effort=` |
| `web_search` | `web_search` tool | `web_search_20260318` tool | WebSearch/WebFetch allowed, else `--disallowedTools` | `-c web_search="live"` / `"disabled"` |
| `max_searches` | `max_tool_calls` | `max_uses` per request, including continuations | stated in the prompt | stated in the prompt |
| `blocked_domains` | `filters.blocked_domains` | `blocked_domains` | stated in the prompt | stated in the prompt |
| `allow_subagents` | n/a | n/a | allow the `Agent` tool; `--agents` file for strategies | `--enable multi_agent` |
| `max_turns` | n/a | n/a | `--max-turns` | n/a |
| cost | estimated from reported tokens and search calls | estimated from reported tokens and search calls | CLI-reported `total_cost_usd` | estimated from reported tokens and observed search calls |

Budget checks use costs already recorded; they do not reserve the next call's maximum cost. A single sequential
call can overshoot, and concurrent calls can overshoot further. Unknown costs contribute zero to totals, so these
are not invoice reconciliations. Returned source URLs support best-effort leakage checks, not a complete record
of every page consulted or of pretraining exposure. Delegation settings permit/request subagents; they do not
prove that the agent spawned one. See the [verification record](../reports/verification_2026-10-22.md).

Anthropic input totals include uncached input, cache reads and cache writes. Supported write TTLs are priced
separately; missing TTL/usage details leave cost unknown. Codex exposes aggregated usage rather than a per-request
invoice, so catalog-based estimates cannot reconstruct every context tier or discount. Interrupted streams retain
available text with unknown cost. The UI, CLI and ledger distinguish known totals from unknown-cost calls.

Agent isolation:
- **Claude Code:** `--setting-sources project --strict-mcp-config --disable-slash-commands --no-session-persistence`,
  plus a `--settings` file with `claudeMdExcludes` (CLAUDE.md, CLAUDE.local.md, AGENTS.md, rules) and
  `autoMemoryEnabled: false`.
- **Codex:** `--ignore-user-config --ignore-rules --ephemeral --skip-git-repo-check`, with the `computer_use`,
  browser, apps, plugins and hooks features disabled, and a `developer_instructions` note telling the agent to ignore
  coding/project instructions from AGENTS.md files. With `AGENT_AUTH=api_key`, `CODEX_HOME` is an empty temporary
  directory, so the global `~/.codex/AGENTS.md` is not loaded.
- **Both:** a fresh temporary working directory per call. With `AGENT_AUTH=subscription`, `ANTHROPIC_API_KEY`,
  `ANTHROPIC_AUTH_TOKEN`, `OPENAI_API_KEY` and `CODEX_API_KEY` are removed from the child environment.

Sources:
- [OpenAI web search guide](https://developers.openai.com/api/docs/guides/tools-web-search)
- [Anthropic web search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool)
- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference)
- [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode) and
  [Codex CLI reference](https://learn.chatgpt.com/docs/cli/reference)

## Persistence

```
logs/<YYYYmmdd_HHMMSS>.log     every log line of the process (terminal mirror)
logs/spend.jsonl               one line per LLM call: ts, label, cost_usd, billed, run_id, backend, model, searches
runs/<run_id>/run.log          only this run's lines (the UI's Live log tab)
runs/<run_id>/run.json         full FactCheckRun (config, iterations, reports, summaries, call records)
runs/<run_id>/report.md        rendered report (CLI)
runs/<run_id>/calls/NNN_<label>.{prompt.md,output.md,result.json,agents.json}
```
