# Auto Fact-Checker

A local, configurable **rigorous fact-checker**. A long expert fact-checking prompt is split into "Lego" blocks.
Each block is a checkbox, slider, dropdown or text box in a Gradio UI. You can run it anywhere from **one
non-agentic API call** up to **Claude Code / Codex agents that spawn subagents**, or **separate calls per claim and
per scientist**. Every claim gets an accuracy score, every verdict label and evaluative condition gets a
**0–100 % score plus a confidence %**, and the corrected text can be re-checked **iteratively** until it is accurate.

![The whole Auto Fact-Checker UI after a run: input text, done/cost status and the Claims table with six scored and corrected claims on the left; preset and settings on the right](docs/images/app.png)

*The UI (full-page capture of a 1920×1080 browser window) after one run on the `ai_research` example, with the
`L1_single_call_search` preset. Left: the input text, the status line with the run's cost, and the **Claims** tab
(accuracy, confidence, claim types, strongest labels and a corrected claim per sentence). Right: the preset and the
settings. The run is described under [Example](#example-the-ai-research-text).*

## Methodology

**1. The prompt as building blocks.** [`prompts/original_prompt.md`](prompts/original_prompt.md) is split into 20
toggleable sections (01–20 in [`prompts/sections/`](prompts/sections)). They are verbatim except for light rewording
where a sentence had to be cut into separate blocks, and the "search the web" wording drops out when web search is
off. Four added sections (00, 21–23) make 24 in total. The added options are:
- the NeurIPS-reviewer role
- claim classification
- 0–100 % scoring
- confidence %

The list-valued parts are editable checkbox groups ([`prompts/options.json`](prompts/options.json)):
- 45 verdict labels
- the degrees fully/partially/slightly
- the style adjectives
- 63 scientists
- claim types

A golden test checks that the all-on prompt still contains every list item and every verbatim sentence of the
original.

**2. Every condition is scored, with confidence.** The prompt asks the model to end with a JSON summary
([`prompts/json_summary.md`](prompts/json_summary.md)). Each claim in that summary has:
- `accuracy_pct` and `confidence_pct`
- claim types, each with a confidence
- every selected verdict label, with a degree, `score_pct` and `confidence_pct`
- every evaluative condition of the original prompt, with a finding, a `score_pct` whose meaning is defined, and a
  `confidence_pct`. The conditions are: omitted nuance, the five strengths/weaknesses pairs, the empiricist,
  rationalist, Bayesian and frequentist perspectives, predictive power, and explanatory power.
- a corrected claim

The summary also contains a corrected whole text and a one-sentence-per-issue list. Claim types, confidences,
labels and conditions are requested only while their sections are switched on; the accuracy, corrected claim,
corrected text and issue list are always requested.

**3. Granular execution: modes are only presets.** A run has five configurable steps: **extract**, **check**,
**perspective**, **synthesize** and **repair** (repair runs only when an answer has no usable JSON summary). Each
step has its own settings:
- API call or agent
- OpenAI or Anthropic
- model (any listed model, with its price)
- reasoning effort ("depth")
- web search on or off, search context size and maximum number of searches
- blocked domains
- whether the agent may spawn subagents
- prompt template (any `.md` in `prompts/<step>/`) or a full prompt override

Two global strategies decide how the text is split into calls:
- **claims:** check the whole text at once, one subagent per claim, or one separate call per claim after
  Claimify-style extraction
- **scientists:** named in the prompt only, one subagent per scientist, or one separate call per scientist

**4. Iteration.** *Iterate until accurate* re-checks the corrected text until every claim reaches the accuracy
threshold. It also stops at the iteration limit, when the corrected text stops changing, or when the budget runs
out. The **One more iteration** button re-checks the latest corrected text once and can be pressed any number of
times.

**5. Evaluation.** A pre-registered benchmark harness compares configurations on the same items. The data is
SciFact claims, labelled SUPPORT vs CONTRADICT. The statistics are balanced accuracy, Wilson CIs, an exact
McNemar test and paired-bootstrap CIs. Dataset hosts are blocked from search (by the API's domain filter; agents get
the rule in their prompt) and every source URL is checked for leakage. Design: [`docs/benchmark.md`](docs/benchmark.md). Results:
[`reports/`](reports). Two further benchmarks score *corrections* rather than verdicts:
- Exp07 judges the correction loop's output against SciFact's gold abstracts ([`docs/correction_eval.md`](docs/correction_eval.md)).
- Exp08 builds its own benchmark: real Wikipedia and arXiv AI-research passages with 0–5 injected, known errors.
  Every correction pass is scored 0–100 against the original passage, comparing a naive and the rigorous prompt
  over 4 forced passes ([`docs/ai_error_bench.md`](docs/ai_error_bench.md)).

## Results so far

These are pre-registered SciFact runs (n = 200 balanced claims, `gpt-6-luna`, one call per claim). Full details
are in [`reports/all_experiments.md`](reports/all_experiments.md) and the paper is
[`reports/paper/paper.pdf`](reports/paper/paper.pdf).

| system | balanced accuracy [95% Wilson CI]¹ | cost / 200 claims |
|---|---|---|
| A simple call, no search | 0.755 [0.691, 0.809] | $0.06 |
| B full rigorous prompt + web search | 0.865 [0.811, 0.906] | $2.97 |
| C simple prompt + web search | 0.890 [0.839, 0.926] | $2.30 |
| D full rigorous prompt, no search (post hoc) | 0.765 [0.702, 0.818] | $0.44 |

¹ Wilson interval of accuracy, which equals balanced accuracy here because the sample is exactly 100 / 100.

On 40 of the same claims (post hoc), agents running the full prompt were not better:
- Codex: balanced accuracy 0.876
- Claude Code with Haiku: 0.797. Its AUROC of 0.962 is above A, D and E but below B (0.978) and C (0.992) on the
  same 40 claims.

- **Web search is what helps.** B beats A by +0.110 [+0.062, +0.160] (McNemar p = 2.7 × 10⁻⁵), and search alone
  explains it (C − A = +0.135).
- **The rigorous prompt does not change verdict accuracy** with search (B − C = −0.025 [−0.061, +0.010]) or without
  it (D − A = +0.010).
- **The prompt's added value is the richer qualitative output**: label and condition scores with confidences,
  corrections and issue lists. SciFact does not measure that.

**Does "iterate until accurate" produce correct text?** Only partly (Exp07, pre-registered). A Codex agent with
web search, looping on 100 claims and judged against the gold evidence:
- raised correctness from 49% to 62%
- labelled every one of its answers correct, although only 62% were
- gained nothing from passes after the first correction

Treat the loop's "accurate" label as a claim to verify, not a verification.

**Does correcting several times beat correcting once?** No (Exp08, pre-registered, our own benchmark). The
benchmark has 20 Wikipedia/arXiv AI-research passages with 48 injected errors. A Codex agent with web search was
forced through 4 passes and scored 0–100 against the original passage:

| prompt | corrupted → pass 1 → pass 4 | injected errors fixed, pass 1 → 4 |
|---|---|---|
| naive ("Fact-check the following text.") | 38.6 → **90.4** → 89.4 | 0.96 → 0.97 |
| full rigorous prompt | 40.0 → **85.7** → 86.2 | 0.97 → **0.90** |

- One pass does the work.
- Further passes add nothing. Under the rigorous prompt they erode fixes (pre-registered); post hoc, the lost fixes
  were hedged or dropped correct facts, while the text grew 62%.
- The naive prompt is at least as good and 6× faster.

The whole project, from implementation through evaluation, cost $7.35 in billed API calls (`uv run afc spend`).

## Quick start

```bash
git clone https://github.com/BurnyCoder/auto-fact-checker && cd auto-fact-checker
uv sync                      # creates .venv with Python 3.13 and the runtime dependencies (+ --group docs/paper)
cp .env.example .env         # then put your OPENAI_API_KEY / ANTHROPIC_API_KEY in .env
uv run afc ui                # opens http://127.0.0.1:7860
```

Optional, needed only for agent steps:
- [Claude Code](https://code.claude.com/docs/en/setup) (`claude`) and/or
  [Codex CLI](https://learn.chatgpt.com/docs/cli) (`codex`) on `PATH`, logged in.
- With `AGENT_AUTH=subscription` (the default), API keys are removed from the agents' environment, so agents use
  those logins. Set `AGENT_AUTH=api_key` to bill the keys instead.

Command line:

```bash
uv run afc check examples/ai_research.md --preset L1_single_call_search
uv run afc check my.txt --preset L4_extract_then_agent_per_claim --set steps.check.model=gpt-6.1-sol --iterations 3
uv run afc spend             # cumulative billed spend vs SPEND_LIMIT_USD
uv run afc bench --systems configs/bench/baseline.json configs/bench/full_single_openai.json --n 20 --max-cost 1 --out reports/results/demo
```

## Example: the AI research text

This is one run of the default preset `L1_single_call_search` on
[`examples/ai_research.md`](examples/ai_research.md):
- one `gpt-6-luna` call with web search, over the whole text, with the full prompt
- 3 searches, $0.039
- run `20261017_210452_941192_the-transformer-architec`

The screenshot at the top of this README shows its **Claims** tab. Against the answer key in
[`docs/examples.md`](docs/examples.md):
- The two fully accurate claims (Transformer 2017, GPT-3 175B) got 99% and 95%.
- Two of the planted errors scored low. "RLHF invented by OpenAI in 2022" got 15%, with the correction citing
  Christiano et al. 2017. "Emergent abilities proven to be phase transitions" got 5%.
- The third planted error, "loss decreases exponentially", was corrected to Kaplan et al.'s power laws. It still
  scored 68%, while the key calls it inaccurate.
- The Chinchilla rule of thumb got 91%. The correction calls the ratio an approximate heuristic, not a universal
  constant, as the key does.

This is a single run, shown to illustrate the outputs. The measured accuracy is in [Results so far](#results-so-far).

The **Corrected text** tab holds the rewritten text, which **One more iteration** checks again:

![Corrected text tab: the rewritten passage with power laws, RLHF history and the contested status of emergence](docs/images/example_corrected.png)

<details>
<summary>The <b>Report</b> tab: the model's full answer (top part)</summary>

![Report tab: per-claim findings with linked sources, scores and corrected claims](docs/images/example_report.png)

</details>

[`docs/scripts/take_screenshots.py`](docs/scripts/take_screenshots.py) makes these screenshots. It starts the UI,
operates it with headless Playwright like a user would, and makes this one paid call. Without `--channel` it uses
Playwright's Chromium, which needs `uv run --group docs playwright install chromium` once.

```bash
uv run --group docs python docs/scripts/take_screenshots.py --channel msedge
```

## Features

**Every block of the original prompt is a toggle**:
- the sentence sections
- the verdict labels, degrees, style words, scientists and claim types, each list extendable with your own items
- a custom-instructions box

**Scores and confidence per claim, label and condition**:
- Labels can be scored for every label, or only for the labels that apply.
- An optional per-scientist "standards" condition can be added.
- The UI shows Claims, Labels and Conditions tables.

**Per-step backends**:

| step kind | OpenAI | Anthropic |
|---|---|---|
| API call | Responses API + hosted `web_search` | Messages API + `web_search_20260318` |
| agent | Codex CLI `codex exec` (live search) | Claude Code `claude -p` (WebSearch/WebFetch, subagents via `--agents`) |

**Strategies**:
- whole text, one subagent per claim, or one separate call per claim
- one subagent per scientist, or one separate call per scientist
- one independent call per **scientist button** in the UI, plus "Synthesize perspectives"

**Presets L0–L5** (in [`configs/presets/`](configs/presets)) go from a single call without search up to separate
claim × scientist calls. You can save your own.

**Iteration**: iterate until accurate, plus the endless **One more iteration** button.

**Prompt preview**: the exact extract, check and perspective prompts (for the first perspective scientist) the
configuration would send, and the `--agents` JSON.

**Logging**:
- Timestamped `logs/<time>.log` and terminal output in real time.
- Every prompt and output in full, never truncated.
- A per-run `runs/<id>/run.log` (its last 80,000 characters are shown live in the UI) and per-call artifact files.

**Cost control**:
- Price catalog for all models.
- Per-run budget.
- Persistent ledger `logs/spend.jsonl` with a global `SPEND_LIMIT_USD` cap, checked before every call. It is a
  soft cap: parallel in-flight calls can overshoot slightly.
- Claude Code `--max-budget-usd`, and search caps (`max_tool_calls` / `max_uses`).

**Benchmark harness**: resumable, cost-capped, paired statistics, leakage flags.

## Technologies

Python 3.13 and [uv](https://docs.astral.sh/uv/) ·
[Gradio 6](https://www.gradio.app/) ·
[OpenAI Python SDK](https://github.com/openai/openai-python) (Responses API) ·
[Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) ·
[Claude Code](https://code.claude.com/docs/en/headless) and [Codex CLI](https://learn.chatgpt.com/docs/non-interactive-mode) ·
pydantic / pydantic-settings · Jinja2 · json-repair · psutil ·
pandas + pyarrow (SciFact parquet) · scikit-learn · statsmodels · SciPy · pytest ·
matplotlib and [Typst](https://typst.app/) (report figures and paper, `--group paper`) ·
[Playwright](https://playwright.dev/python/) (README screenshots only, `--group docs`).

## What happens when you run it

1. **Configuration.** The UI widgets (or a preset plus `--set` overrides) become one `FactCheckConfig`.
2. **Run record.** `pipeline.run_fact_check` creates a run (`runs/<run_id>/`) and a `RunContext`. That context is
   the only path to the LLMs. For each call it:
   - checks the global spend cap and the per-run budget
   - logs the full prompt
   - writes `calls/NNN_<label>.prompt.md`
   - calls the backend
   - logs the full output, tokens, searches, cost and sources
   - writes `.output.md` and `.result.json`
   - appends to `logs/spend.jsonl`
3. **One iteration.** The input is the original text, or the latest corrected text.
   1. If the claim strategy is *one separate call per claim*: the **extract** step returns self-contained claims.
   2. **check** calls run in parallel (`max_parallel`): one per target, i.e. the whole text or each claim. With
      *one separate call per scientist*, each target also gets one **perspective** call per scientist.
   3. With subagent strategies, a single Claude Code agent receives an orchestration prompt plus a `--agents` file,
      and spawns `claim-checker` / `scientist-perspective` subagents itself.
   4. Every answer's JSON summary is parsed tolerantly. If it is missing, the **repair** step extracts it (unless
      repair is switched off or the call itself failed, e.g. a refusal).
   5. **synthesize** merges per-scientist results per claim, then all claims into one report with a corrected
      whole text.
4. **Stopping.** `iterate.should_stop` decides whether to run another pass (threshold, fixed point, missing
   summary, no corrected text); budget and Stop are enforced per call by `RunContext`. The UI shows the result in
   tabs:
   - Report, Claims, Labels, Conditions, Corrected text, Issues
   - Iterations, Perspectives, Calls & cost, Live log
   - Prompt preview, Raw JSON

## Architecture

```mermaid
flowchart LR
  UI[ui.py Gradio widgets] --> CFG[config.FactCheckConfig<br/>per-step StepConfig]
  CLI[__main__.py afc check / bench] --> CFG
  CFG --> PIPE[pipeline.py<br/>run_fact_check / run_iteration]
  PIPE --> EX[phases/extract] & CH[phases/check] & SY[phases/synthesize] & IT[phases/iterate]
  CH --> RP[phases/check.summarize_output<br/>+ repair step]
  EX & CH & SY & RP --> PR[prompts.py<br/>sections + options + templates]
  EX & CH & SY & RP --> CTX[context.RunContext.call<br/>logs · artifacts · budget · Stop]
  CTX --> REG[backends registry]
  REG --> OA[openai_api<br/>Responses + web_search]
  REG --> AA[anthropic_api<br/>Messages + web_search]
  REG --> CC[claude_code<br/>claude -p + --agents]
  REG --> CX[codex<br/>codex exec --json]
  CC & CX --> SUB[subprocess_jsonl<br/>Windows-safe streaming]
  CTX --> LED[(logs/spend.jsonl)] & RUNS[(runs/&lt;id&gt;/)]
  BENCH[bench/run.py] --> PIPE
  BENCH --> MET[bench/metrics.py]
```

More detail is in [`docs/architecture.md`](docs/architecture.md). Every setting is listed in
[`docs/configuration.md`](docs/configuration.md).

## Costs and safety

- The default models are the cheapest: `gpt-6-luna` ($0.10/$0.50 per 1M tokens) and `claude-haiku-5-5`
  ($0.10/$0.50). Web search costs about $0.01 per search with both providers, and that dominates the cost of a
  call. All prices are in `src/auto_fact_checker/catalog.py`, with source links.
- Agents run **without permission prompts or a sandbox**, as the project specifies
  (`--dangerously-skip-permissions`, `--dangerously-bypass-approvals-and-sandbox`). The measures that are not
  sandboxing:
  - each agent runs in a fresh temporary directory
  - Claude Code loads only project settings (`--setting-sources project`), so your user settings and the plugins
    they enable are skipped. It also gets `--strict-mcp-config` (no MCP servers), `--disable-slash-commands`, and a
    `--settings` file that excludes CLAUDE.md/AGENTS.md files and turns auto-memory off. Organization-managed
    settings and CLAUDE.md still apply.
  - Codex gets `--ignore-user-config` (no `config.toml`), `--ignore-rules`, and its desktop/browser-control,
    apps, plugins and hooks features off. Your global `~/.codex/AGENTS.md` is only excluded in `AGENT_AUTH=api_key`
    mode (empty `CODEX_HOME`). In both modes a developer instruction tells the agent to ignore coding, git and
    project-setup instructions from AGENTS.md files.
  - API keys are stripped in subscription mode
  - the checked text is wrapped in tags; the default templates also tell the model to treat it as data
    (`check/minimal_baseline.md`, `extract/simple_list.md` and `repair/repair_json.md` only wrap it)
  - budgets and timeouts apply
  - the UI only listens on 127.0.0.1. Gradio's telemetry and version check contact api.gradio.app unless you set
    `GRADIO_ANALYTICS_ENABLED=False` in the environment (the test suite does)

  Web pages or the text being checked can still contain prompt injections aimed at an agent that has shell access.
  Do not run agent steps on machines holding secrets you cannot risk.

## Repository layout

```
prompts/        original prompt, sections/, options.json, json_summary.md, per-step templates (check/ extract/ …)
configs/        presets/ (UI "modes") and bench/ (pre-specified benchmark systems)
src/auto_fact_checker/
  config.py catalog.py spend.py logs.py prompts.py schema.py results.py context.py render.py
  pipeline.py (the wrapper)  phases/  backends/  bench/  ui.py  __main__.py
examples/       AI research / philosophy / engineering texts with planted errors (answer key: docs/examples.md)
benchmarks/     ai_errors_v1/: frozen Exp08 dataset (Wikipedia + arXiv passages with injected errors)
docs/           architecture, configuration, the three pre-registrations (benchmark.md, correction_eval.md,
                ai_error_bench.md), example answer key; images/ (UI screenshots) and scripts/take_screenshots.py
                which makes them
reports/        experiment reports, all_experiments.md, paper/
tests/          offline pytest suite (fake backend) + live tests (`-m live`)
```

## Tests

```bash
uv run pytest            # offline: fake backend, no LLM or network call, no cost
uv run pytest -m live    # real calls to gpt-6-luna / claude-haiku-5-5 / claude / codex (a few cents)
```

## Data and licences

SciFact (Wadden et al., 2020) is CC BY-NC 2.0 ([dataset card](https://huggingface.co/datasets/allenai/scifact)) and
is downloaded at run time from the
[Hugging Face parquet export](https://huggingface.co/datasets/allenai/scifact/tree/refs%2Fconvert%2Fparquet). Claim extraction follows Claimify
(Metropolitansky & Larson, 2025, [arXiv:2502.10855](https://arxiv.org/abs/2502.10855)). The Exp08 passages come from
Wikipedia lead sections ([CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/); the corrupted versions are
adaptations under the same licence) and arXiv abstracts (arXiv dedicates its metadata to
[CC0 1.0](https://info.arxiv.org/help/license/index.html) without saying whether that covers abstracts; each item
links its paper, whose licence is shown there).
