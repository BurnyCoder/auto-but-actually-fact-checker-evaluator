# Configuration reference

Every field below is a widget in the UI. The UI generates its widgets from these fields, so this list is complete
by construction. Each field is also a key in preset JSON and in `afc check --set key=value`.

## Per-step settings (`steps.<extract|check|perspective|synthesize|repair>.*`)

| field | values | meaning |
|---|---|---|
| `enabled` | bool | skip the step. Extract off → whole text. Synthesize off → deterministic merge. Repair off → no JSON repair. Check off → only per-scientist calls run. |
| `kind` | `api` / `agent` | one provider API request, or a CLI agent run |
| `provider` | `openai` / `anthropic` | api+openai = Responses API, api+anthropic = Messages API, agent+openai = Codex, agent+anthropic = Claude Code |
| `model` | any id | dropdown of `catalog.MODELS` with prices; custom ids allowed |
| `effort` | none … max | reasoning depth |
| `web_search` | bool | enables the provider's search tool; also turns the "search the web" sentences of the prompt on or off |
| `search_context_size` | low/medium/high | OpenAI search context size |
| `max_searches` | 0–50 | search cap (see [architecture](architecture.md#how-the-backends-map-the-settings)) |
| `blocked_domains` | comma list | excluded from search (API backends) |
| `allow_subagents` | bool | agents may spawn subagents (subagent strategies require a Claude Code check agent) |
| `max_subagents` | 1–30 | upper bound stated to the orchestrating agent |
| `max_turns` | 0 = unlimited | Claude Code `--max-turns` |
| `timeout_s` | seconds | agents: wall-clock limit, the process tree is killed; API calls: SDK request timeout |
| `prompt_template` | file in `prompts/<step>/` | e.g. `check/rigorous_sections.md`, `minimal_baseline.md`, `neurips_review.md`; `extract/claimify.md`, `simple_list.md` |
| `prompt_override` | Jinja text | replaces the template. Variables include `text`, `context`, `persona`, `sections_text`, `output_contract`, `reports`, `report`, the option lists, and the `web_search` / `confidence` / `classify` / `labels_on` flags |

Defaults: every step uses an OpenAI API call to `gpt-6-luna` with effort `low`. Web search is on only for `check`
and `perspective`.

## Global settings

| field | meaning |
|---|---|
| `claim_strategy` | `whole_text` · `subagent_per_claim` (check must be an agent with `allow_subagents`) · `separate_call_per_claim` (extract → one check per claim → synthesis) |
| `scientist_strategy` | `none` (scientists only named in-prompt, via section 11) · `subagent_per_scientist` · `separate_call_per_scientist` (one perspective call per scientist per target) |
| `perspective_scientists` | scientists for the per-scientist strategies and the UI's perspective buttons |
| `sections` | which prompt blocks go in (24 sections; NeurIPS role off by default) |
| `conditions` | which scored conditions are requested (only while their section is on) |
| `score_all_labels` | score every selected label per claim (default), or only those that apply |
| `score_each_scientist` | add one scored "<scientist>'s standards" condition per named scientist |
| `verdict_labels`, `degrees`, `styles`, `claim_types`, `scientists` | the lists rendered into the sections; extendable |
| `custom_instructions` | appended after the sections |
| `max_claims`, `max_parallel` | extraction cap; number of concurrent calls |
| `iterate_until_accurate`, `accuracy_threshold`, `max_iterations`, `stop_on_fixed_point` | iteration control |
| `max_cost_usd` | per-run budget (the global `SPEND_LIMIT_USD` applies on top) |

## Scored conditions

The 12 conditions and the meaning of each 0–100 % score are defined in `prompts/options.json["conditions"]`:

| condition | section | score_pct means |
|---|---|---|
| omitted nuance, context and complexity | 04 | how much important nuance is omitted (0 = none) |
| strengths and weaknesses · advantages and disadvantages · limitations and potentials · ups and downs · good and bad | 06 | 0 = only the negative pole, 100 = only the positive pole |
| empiricist perspective · rationalist perspective | 07 | how well the claim holds up under each epistemology |
| Bayesian perspective | 08 | posterior probability that the claim is true |
| frequentist perspective | 08 | support from frequentist evidence (significance, effect sizes, replication) |
| predictive power · explanatory power | 10 | how many testable predictions · how much is explained with how few assumptions |

## `.env`

| variable | default | meaning |
|---|---|---|
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | – | API keys (read with pydantic-settings, never exported) |
| `ANTHROPIC_WORKSPACE_ID` | – | sent as `anthropic-workspace-id`; required for keys not scoped to a workspace |
| `AGENT_AUTH` | `subscription` | `subscription` strips the keys from agent processes; `api_key` passes them (Codex receives `CODEX_API_KEY`) |
| `SPEND_LIMIT_USD` | `10` | global cap on billed spend in `logs/spend.jsonl`, checked before every call (soft: in-flight parallel calls can overshoot; uncatalogued models count as $0 with a warning) |
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
