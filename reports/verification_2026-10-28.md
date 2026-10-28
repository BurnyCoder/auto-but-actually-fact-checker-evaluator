# Independent verification record — 2026-10-28

This record replaces `verification_2026-10-22.md`. It was made without reading or trusting that earlier audit.

## Scope and method

The audit checked every claim in the following material:
- README.md and AGENTS.md
- docs/
- reports/: the experiment reports, all_experiments.md, the paper and the subagent record
- benchmarks/ai_errors_v1/README.md
- code docstrings, comments and UI labels

Three independent read-only passes were run, and their key findings were then spot-checked by hand:
1. **Docs against code.** Every named function, flag, default, count, path and link was compared with `src/`, `prompts/`, `configs/` and `git ls-files`.
2. **Numbers against raw records.** Every reported number was recomputed from the committed `reports/results/**/*.jsonl` with `auto_fact_checker.bench.metrics` and the analysis functions. The local `runs/` and `logs/spend.jsonl` were used where noted. Nothing was rewritten.
3. **External claims against primary sources,** fetched on 2026-10-28: provider docs and pricing, CLI references, dataset cards and licences, papers, and the installed package source.

No paid model call was made.

The 30 frozen evidence files still match the [SHA-256 manifest](results/evidence_hashes_2026-10-22.json) (`tests/test_evidence.py`).

## What reproduced exactly

Every primary statistic reproduces from the raw records.

| claim | recomputed |
|---|---|
| Balanced accuracy [Wilson 95%], n = 200 | A 0.755 [0.691, 0.809], B 0.865 [0.811, 0.906], C 0.890 [0.839, 0.926], D 0.765 [0.702, 0.818] |
| Paired Δ and exact McNemar | B−A +0.110 [+0.062, +0.160], 3/25, p = 2.7×10⁻⁵; C−A +0.135, 2/29, p = 4.6×10⁻⁷; B−C −0.025 [−0.061, +0.010], 9/4, p = 0.27; D−A +0.010 [−0.026, +0.047], 6/8, p = 0.79; B−D +0.100, 2/22, p = 3.6×10⁻⁵ |
| AUROC / Brier, A–F | 0.844/0.165; 0.944/0.101; 0.956/0.087; 0.891/0.142; 0.917/0.113; 0.962/0.161 |
| 40-claim subset | E BA 0.876, F BA 0.797; AUROC B 0.978, C 0.992, F 0.962 |
| Costs, A–D (200 claims) | $0.063 / $2.97 / $2.30 / $0.44 |
| Exp07 | 49% → 62%, +0.13 [+0.02, +0.24], 10/23, p = 0.035; self-label 100/100, precision 62% [52, 71]; H3 +0.01 [−0.06, +0.08] |
| Exp08 | 38.6 → 90.4 → 89.4 and 40.0 → 85.7 → 86.2; 44/48 and 45/48 fully corrected; weighted fix 0.958 / 0.969; per-passage fix rate (rigorous) −0.067 [−0.117, −0.022], p = 0.015 |
| Sampling | SciFact pool 124+332 / 64+173 and the seed-0 sample reproduce `items.json`; pre-registration commits precede the first paid call |
| Benchmark README | 20 passages, 48 edits, k 0–5, error-type counts, licences |

Two notes on the statistics:
- **Seed:** the B−A bootstrap interval depends on item order as well as on seed 0. Items-file order gives [0.0625, 0.1595]; sorted ids give [0.0617, 0.1604]. Both round to the reported [+0.062, +0.160].
- **Wilson interval:** it is an interval for accuracy. Accuracy equals balanced accuracy at the 100/100 split, and the interval is at most marginally conservative for balanced accuracy.

## Findings and fixes

Commits are on branch `fix/independent-fact-check-2026-10-28`.

### Code behaviour

| finding | evidence | fix |
|---|---|---|
| OpenAI cache writes were unpriced. GPT-5.6+ bills them at 1.25× input (30 min) or 2.5× (12 h). | [Prompt-caching guide](https://developers.openai.com/api/docs/guides/prompt-caching), [pricing page](https://developers.openai.com/api/docs/pricing) (gpt-6-luna $0.125 / $0.25 per 1M) | Per-model write multipliers, tested (`45fa0c6`) |
| `afc ai-errors build` defaulted `--out` to the frozen `benchmarks/ai_errors_v1`. A test of the bare command started a real fetch toward it, which failed before writing. | `bench/ai_errors.py` argparse | `--out` required, tested (`ba8ed27`) |
| The comment said "json.dumps output is a valid TOML basic string", but a raw U+007F is rejected. | `tomllib`: "Illegal character '\x7f'" | `toml_str` escapes it, tested (`17ef43e`) |
| Codex subagent roles lacked the AGENTS.md developer note, contrary to the README. | `role_toml` set `developer_instructions` to the subagent prompt only | Note prepended, tested (`17ef43e`) |

**Historical costs.** The 1,781 recorded `openai_api` calls (all `gpt-6-luna`) total $7.21. If every uncached input token had been a 30-minute cache write, they would have cost at most **$0.17** more. Historical records are not rewritten.

### Docs and comments (`f54b889`, `b3ae79b`)

- **SciFact licence.** The [HF card](https://huggingface.co/datasets/allenai/scifact) says CC BY-NC 2.0. The upstream [LICENSE.md](https://github.com/allenai/scifact/blob/master/LICENSE.md) says CC BY 4.0 for claims and annotations, and ODC-By 1.0 for the S2ORC abstracts. The README and `datasets.py` now state both.
- **Gradio 6.30 network calls.** The version check goes to `api.gradio.app/pkg-version`. Usage telemetry goes through `huggingface_hub` as a HEAD request to `huggingface.co/api/telemetry/…`. Both are off with `GRADIO_ANALYTICS_ENABLED=False`. Source: the installed `gradio/analytics.py` and `huggingface_hub/utils/_telemetry.py`. The README previously said both contacted api.gradio.app.
- **README Exp08 table.** The column labelled "mean per-passage fix score" held the weighted 48-edit score. The column is renamed, and the pre-registered per-passage fix rate (0.978 → 0.911 rigorous) is now reported separately.
- **"62% longer than the original references" is 61%.** Rigorous pass 4 averages 253.65 words; the originals average 157.45 and the corrupted inputs 157.05.
- **Templates.** `repair/repair_json.md` is the default repair template. It wraps the model's report and carries no treat-as-data line.
- **`--strict-mcp-config`.** It makes Claude Code exit when an organization [`managed-mcp.json`](https://code.claude.com/docs/en/managed-mcp) exists.
- **Codex rollouts** persist only in subscription mode. In `api_key` mode the temporary `CODEX_HOME` is deleted.
- **"2 of 6 / 4 of 6 spawns failed" has no supporting artifact.** The matrix shows 3 failures (row c7) and 2 (row c12).
- **`claudeMdExcludes` via `--settings`.** The docs list the user/project/local/managed layers only. That it works through `--settings` is supported by the live canary test, not by the docs.
- **Pre-registration pages.** Each claimed a single later edit, or complete inline markers. They now carry amendment logs listing every later commit, including the unmarked rewrites. One example: the dropped sentence that the Exp07 judge "biases H1 *against* the loop".
- **Smaller fixes:**
  - the configuration table rendering
  - the HF parquet link
  - `uv sync` also installs the dev group
  - SciPy is used only by the report scripts
  - the architecture diagram now shows synthesize → repair and the bench judges
  - `_pct`, logger names, `max_subagents` and the spend-check scope are described as they behave
  - the `gpt-6.1-sol` label now reads "near-Astra", per the [models page](https://developers.openai.com/api/docs/models)
- **Repository rename.** The repository is now `BurnyCoder/auto-but-actually-fact-checker-evaluator` (confirmed with `gh repo view`). Links and the User-Agent follow it; old URLs redirect.

Source links were added where library behaviour was used without one:
- Gradio queue, Dataframe and CheckboxGroup
- Claude effort and cache-usage fields
- `claude --help` v2.1.312 flag semantics
- the gpt-6-luna effort levels
- the `datasets` 4.0 removal of loading scripts
- the Wikimedia User-Agent policy
- Claimify

### Reports and paper (`fee5740`)

- **Paper abstract.** −0.067 [−0.117, −0.022] is the per-passage fix rate, not the weighted fix score.
- **Paired Δ AUROC intervals are post hoc.** The pre-registration `378c59b` lists AUROC per system only; the paired bootstrap arrived in `c15c0cb`.
- **"Search explains essentially all of it" overclaimed.** D − A [−0.026, +0.047] does not exclude a prompt effect of about +5 points.
- **Exp07 report.** It named one later script change, but there were two (`a8916a0`, `141ba36`); neither changed a statistic. The unreported leak flag in the Claude arm (train-278, a github.com iGEM wiki page) is now reported.
- **Overgeneralised summary heading.** It said "iteration erodes annotated specifics", but only the rigorous arm eroded.
- **Transformer BLEU.** The conflict now lists all three values: 41.0 in the [arXiv v7](https://arxiv.org/abs/1706.03762) §6.1 prose, 41.8 in its abstract and Table 2, and 41.1 in the [NeurIPS abstract](https://papers.nips.cc/paper_files/paper/2017/hash/3f5ee243547dee91fbd053c1c4a845aa-Abstract.html). `exp08_posthoc.py` keeps its accurate v7 description.
- **Rounding.** Exp00 $0.53 → $0.52; Exp02 mean searches 1.03 → 1.04 (207 / 200); naive pass-1 length 150 → 151 (half-up, as elsewhere).
- **Ledger.** The total is now dated: $7.34726649 over 2,953 entries on 2026-10-22, and $7.55085675 over 3,004 entries on 2026-10-28, with one entry of unknown cost.
- **Citations added:**
  - Wilson 1927 ([doi](https://doi.org/10.1080/01621459.1927.10502953))
  - Wilcoxon 1945 ([doi](https://doi.org/10.2307/3001968))
  - Efron & Tibshirani, *An Introduction to the Bootstrap* ([doi](https://doi.org/10.1201/9780429246593))
  - the FIRE venue (Findings of NAACL 2025, from its arXiv comment)
- **AI statement** added at the end of the paper.

## Confirmed external claims (2026-10-28)

**Prices.** [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing), per 1M tokens:

| model | input / output | cache read | other |
|---|---|---|---|
| Haiku 5.5 | $0.10 / $0.50 | $0.01 | over 100K tokens: $0.50 / $2.50 / $0.05 |
| Sonnet 5.5 | $2 / $10 | $0.10 | |
| Opus 5.5 | $4 / $20 | $0.20 | |
| Fable 5.1 | $10 / $50 | $0.25 | |

- Cache writes cost 1.25× input (5 min) or 2× (1 h).
- Web search costs $10 per 1,000 searches on both providers.
- The OpenAI catalog rows, including the over-272K tier, match the [pricing page](https://developers.openai.com/api/docs/pricing).

**APIs and CLIs**
- `web_search_20260318`, `max_uses` per request, `allowed_callers`, and `pause_turn` continuation: [web search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool).
- OpenAI `web_search` filters and `max_tool_calls`: [guide](https://developers.openai.com/api/docs/guides/tools-web-search).
- Claude Code flags: [CLI reference](https://code.claude.com/docs/en/cli-reference) and `claude --help` 2.1.312.
- Codex flags and config keys: [CLI reference](https://learn.chatgpt.com/docs/cli/reference).

**Data and papers**
- The SciFact parquet counts match.
- arXiv metadata, including abstracts, is [CC0 1.0](https://info.arxiv.org/help/license/index.html).
- Wikipedia text is CC BY-SA 4.0.
- Every `refs.yml` entry matches its arXiv, ACL Anthology, DOI or NCBI record.
- Claimify has separate selection, disambiguation and decomposition stages, and drops opinions ([paper](https://arxiv.org/html/2502.10855v2)).
- The example answer key is correct on these points: Kaplan power laws; Chinchilla 70B with 1.4T tokens; RLHF from Christiano et al. 2017; LoRA's frozen base weights; FlashAttention's compute and memory.

## Not verified

- Whether `--setting-sources project` also skips plugins enabled in user settings, and user subagents in `~/.claude/agents/`. The docs are silent.
- Whether `codex exec` rejects `--search`. It is listed only as a global flag.
- From earlier records with no stored data:
  - Exp03's pre-rerun 0.760 / 0.888
  - Exp05's earlier second refusal
  - the Exp07 "pass 7–8 / 20 minutes" stop observation (logs show about 3.3 minutes per pass)
  - the 72/35 combination sweep and the 1,800/4,500-state UI fuzz runs in the subagent record
  - the Exp00 UI-check costs
- Whether the historical OpenAI API calls actually wrote to the cache. Only the upper bound above can be computed.
