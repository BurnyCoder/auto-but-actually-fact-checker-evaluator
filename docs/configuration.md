# Configuration reference

Every field below is a widget in the UI (`tests/test_ui.py` checks that every config field has one); this table is
kept in sync by hand. Each field is also a key in preset JSON and in `afc check --set key=value`. Ranges are the UI
slider ranges (`ui.RANGES`).

## Per-step settings (`steps.<extract|check|perspective|synthesize|repair>.*`)

| field | values | meaning |
|---|---|---|
| `enabled` | bool (on) | skip the step. Extract off → whole text. Check off → only per-scientist calls run. Perspective off → no per-scientist calls (the UI's perspective buttons still run). Synthesize off → several results are merged deterministically, without a corrected whole text, so iteration stops. Repair off → no JSON repair. |
| `kind` | `api` / `agent` (api) | one API conversation turn (Anthropic may continue paused turns), or a CLI agent run |
| `provider` | `openai` / `anthropic` (openai) | api+openai = Responses API, api+anthropic = Messages API, agent+openai = Codex, agent+anthropic = Claude Code |
| `model` | any id | dropdown of `catalog.MODELS` with prices; custom ids allowed |
| `effort` | none … max (low) | reasoning depth; Anthropic/Claude Code map none/minimal → low, and a model rejects levels it lacks (gpt-6-luna has no minimal) |
| `web_search` | bool | enables the provider's search tool; also turns the "search the web" sentences of the prompt on or off |
| `search_context_size` | low/medium/high (medium) | OpenAI search context size |
| `max_searches` | 0–50 (5) | API tool-call/use limit (Anthropic: per request, including continuations); an agent prompt instruction rather than enforced agent-wide cap (see [architecture](architecture.md#how-the-backends-map-the-settings)) |
| `blocked_domains` | comma list (empty) | excluded from search: by the provider's domain filter for API steps, as a prompt instruction for agents |
| `allow_subagents` | bool (off) | agents may spawn subagents (Claude Code `Agent` tool; Codex `multi_agent` without `--ephemeral`, which breaks `spawn_agent`). Always on for the check step under a subagent strategy |
| `max_subagents` | 1–30 (8) | upper bound stated to the orchestrating agent; for Codex also `agents.max_concurrent_threads_per_session` (with the default, 2 of 6 parallel spawns failed) |
| `max_turns` | 0–300 (0 = unlimited; `null` in JSON) | Claude Code `--max-turns` |
| `timeout_s` | 60–7200 s (900) | agents: wall-clock limit, the process tree is killed; API calls: SDK request timeout |
| `prompt_template` | file in `prompts/<step>/` | e.g. `check/rigorous_sections.md`, `minimal_baseline.md`, `neurips_review.md`; `extract/claimify.md`, `simple_list.md` |
| `prompt_override` | Jinja text | replaces the template (and, for subagent strategies, the orchestrator wrapper). Variables include `text`, `context`, `persona`, `sections_text`, `output_contract`, `reports`, `report`, the option lists, and the `web_search` / `confidence` / `classify` / `labels_on` flags. A syntax error or unknown variable is rejected when the settings are validated (before any call), naming `steps.<step>.prompt_override` |

Defaults: every step uses an OpenAI API call to `gpt-6-luna` with effort `low`. Web search is on only for `check`
and `perspective`.

## Global settings

| field | meaning |
|---|---|
| `claim_strategy` | `whole_text` (default) · `subagent_per_claim` (check must be an agent: Claude Code or Codex) · `separate_call_per_claim` (extract → one check per claim → synthesis) |
| `scientist_strategy` | `none` (default; scientists only named in-prompt, via section 11) · `subagent_per_scientist` (check must be an agent) · `separate_call_per_scientist` (one perspective call per scientist per target) |

In the UI, an edit that would make the configuration invalid adjusts the conflicting setting instead and shows a
note (`config.fix_combination`). The setting you just edited is never changed:
- Picking a subagent strategy makes the check step an agent. Switching the check step back to an API call maps
  subagent strategies to their separate-call equivalents.
- Picking a catalogued model selects its provider. Picking a provider selects its default model.
- Unticking the check step switches on one separate perspective call per scientist. Any edit that would leave
  nothing to run re-enables the check step.

The CLI and presets are not adjusted: they get the validation error.
| `perspective_scientists` | scientists for the per-scientist strategies and the UI's perspective buttons (Karl Popper, Richard Feynman, Andrew Gelman) |
| `sections` | which prompt blocks go in (24 sections; NeurIPS role off by default) |
| `conditions` | which scored conditions are requested (only while their section is on) |
| `score_all_labels` | score every selected label per claim (default), or only those that apply |
| `score_each_scientist` | off by default; add one scored "<scientist>'s standards" condition per named scientist |
| `verdict_labels`, `degrees`, `styles`, `claim_types`, `scientists` | the lists rendered into the sections; extendable |
| `custom_instructions` | appended after the sections |
| `max_claims`, `max_parallel` | extraction cap, 1–50 (15); number of concurrent calls, 1–16 (4) |
| `iterate_until_accurate`, `accuracy_threshold`, `max_iterations`, `stop_on_fixed_point` | iteration control: off, 90 % (0–100), 3 (1–20), on |
| `max_cost_usd` | per-run soft budget, 0.01–10 (1.0). Counts recorded billed and notional (subscription-agent) cost; the global `SPEND_LIMIT_USD` counts recorded billed cost only. Sequential and concurrent in-flight calls can overshoot |

## Scored conditions

The 12 conditions and the requested meaning of each 0–100 % score are defined in `prompts/options.json["conditions"]`.
These are subjective model assessments, not validated measurements or calibrated probabilities. Optional fields
can be missing from a response; the parser does not establish their factual correctness.

| condition | section | score_pct means |
|---|---|---|
| omitted nuance, context and complexity | 04 | how much important nuance is omitted (0 = none) |
| strengths and weaknesses · advantages and disadvantages · limitations and potentials · ups and downs · good and bad | 06 | 0 = only the negative pole, 100 = only the positive pole |
| empiricist perspective · rationalist perspective | 07 | how well the claim holds up under each epistemology |
| Bayesian perspective | 08 | subjective assessment of support under stated priors and evidence; not a computed or calibrated posterior |
| frequentist perspective | 08 | support from frequentist evidence (significance, effect sizes, replication) |
| predictive power · explanatory power | 10 | how many testable predictions · how much is explained with how few assumptions |

## `.env`

| variable | default | meaning |
|---|---|---|
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | – | API keys (read with pydantic-settings, not exported to the process environment; passed to agent processes only with `AGENT_AUTH=api_key`) |
| `ANTHROPIC_WORKSPACE_ID` | – | sent as `anthropic-workspace-id`; required for keys not scoped to a workspace |
| `AGENT_AUTH` | `subscription` | `subscription` strips the keys from agent processes; `api_key` passes them (Codex receives `CODEX_API_KEY`) |
| `SPEND_LIMIT_USD` | `10` | soft limit on recorded billed cost estimates, checked before every call; even a sequential call can overshoot, and parallel calls can overshoot further. Unknown costs contribute zero with a warning; subscription fees are excluded |
| `CLAUDE_BIN`, `CODEX_BIN` | PATH lookup | explicit `.exe` paths (`.cmd` shims are rejected) |
| `LOGS_DIR`, `RUNS_DIR` | `logs`, `runs` | relative to the repo root |

## Presets (`configs/presets/`)

| preset | what it sets |
|---|---|
| `L0_single_call_no_search` | one non-agentic OpenAI call, no search |
| `L1_single_call_search` | one OpenAI call with hosted web search (default behaviour) |
| `L2_single_agent_codex` / `L2_single_agent_claude` | one agent checks the whole text |
| `L3_agent_subagents_claude` | Claude Code lead agent plus claim-checker and scientist-perspective subagents |
| `L4_extract_then_agent_per_claim` | extract → one Codex agent per claim → synthesis |
| `L5_per_claim_x_scientist_calls` | extract → per claim: a general check plus one API call per perspective scientist → syntheses |

Presets are partial JSON, deep-merged over the defaults. "Save preset" in the UI writes a full configuration.
