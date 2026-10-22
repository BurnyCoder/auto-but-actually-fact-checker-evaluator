# Independent claim verification — 2026-10-22

This verification starts from repository commit `65d6da03d9fafb39729a5ef39be77b7c85897976`.
Earlier audit conclusions were not accepted as evidence. Sources were checked against the implementation,
committed experiment records, independently recomputed statistics, and primary publications/documentation.
The work uses existing evidence and offline tests; it does not add paid model runs or training experiments.

The table below groups repeated claims by their shared evidence. **Supported** means the stated, bounded claim
is supported by the cited evidence; **corrected** identifies a factual or behavioral discrepancy; **qualified**
limits an overstatement; **unresolved** means the available evidence does not decide the claim. These are audit
dispositions, not model accuracy scores. Historical model statements remain observations, not endorsed facts.

## Evidence preservation and reproducibility

- The [SHA-256 manifest](results/evidence_hashes_2026-10-22.json) records 30 frozen dataset/raw-result/item files
  before edits. No frozen passages, injected edits, historical model responses, or saved judge outputs are
  rewritten. Changes to interpretation are dated errata or explicitly post-hoc analyses.
- Primary numerical outputs remain in [SciFact](results/scifact_analysis.json),
  [correction evaluation](results/correction_analysis.json), and [AI-error evaluation](results/ai_errors_analysis.json).
  Their central statistics were independently recomputed from committed per-item records and matched.
- The [Exp08 post-hoc analysis](results/exp08_posthoc.json) adds the ambiguous-edit sensitivity and a separate
  source-verification layer. It retains the original AI-agent classifications as historical annotations.
- Raw `runs/` and `logs/` are local, ignored artifacts. A clean clone can recompute primary metrics from the
  committed records, but cannot reconstruct every original prompt, timing measurement, or billed-cost entry.
  The post-hoc script explicitly reports missing run IDs instead of silently inventing timing/cost data.
- Frozen inputs describe the historical experiment. New prompt wording and runtime fixes change future runs;
  they do not retroactively validate or replace the old runs.

## Product and implementation claims

| Claim and locations | Disposition and correction | Evidence |
|---|---|---|
| README methodology; architecture; AGENTS: modular wrapper and four backends | Supported: `pipeline.py` delegates phases; production calls use `RunContext`; API and CLI backends share request/result types. | [Pipeline](../src/auto_fact_checker/pipeline.py), [registry](../src/auto_fact_checker/backends/__init__.py), pipeline/backend tests. |
| README/configuration: 24 sections, 45 labels, 63 named scientists and configurable prompts | Supported as configuration inventory, not proof that models follow every instruction. | [Options](../prompts/options.json), [section files](../prompts/sections), [prompt tests](../tests/test_prompts.py). |
| README/UI: every claim always receives every field | Qualified: prompts request the fields; tolerant parsing accepts missing values. | [Output contract](../prompts/json_summary.md), [schema](../src/auto_fact_checker/schema.py). |
| README/UI/iteration comments: loop produces accurate text | Qualified: stopping evaluates scores returned by the model, which can omit claims or be wrong; it is not independent verification. | [Stopping policy](../src/auto_fact_checker/phases/iterate.py), [Exp07](experiments/exp07_correction_loop.md). |
| Score parser: missing scores never pass; all percentages are finite | Corrected: missing scores could pass at threshold zero and infinities could become 100. Missing/nonfinite values now cannot satisfy the threshold. | [Schema regressions](../tests/test_schema.py). |
| Confidence and Bayesian assessment are probabilities | Qualified: self-reported confidence and a subjective Bayesian-style assessment, without specified prior/likelihood inference or calibration. `100 − confidence` is no general uncertainty identity. | [Options](../prompts/options.json), [confidence instructions](../prompts/sections/23_confidence.md), [empirical LLM calibration study](https://aclanthology.org/2023.emnlp-main.330/). |
| UI Stop prevents queued work and eventually displays stopped | Corrected: contexts no longer clear another batch's cancellation; queued work retains its batch event; status polling survives Stop. | [Context](../src/auto_fact_checker/context.py), [pipeline/UI regressions](../tests/test_pipeline.py), [UI tests](../tests/test_ui.py). |
| Anthropic Stop and complete real-time text logging | Corrected: consume text events, log deltas and check Stop before requests and during streams; preserve observed partial text on cancellation. Cancellation is cooperative and does not promise reversal of server billing. | [Backend regressions](../tests/test_backend_integrity.py), [SDK streaming helpers](https://github.com/anthropics/anthropic-sdk-python/blob/main/helpers.md#streaming-responses). |
| Anthropic search cap applies to the entire logical call | Qualified: `max_uses` is per request, including each continuation. Agent limits stated in prompts are not enforced API limits. | [Web search parameter contract](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool), [continuation contract](https://platform.claude.com/docs/en/agents-and-tools/tool-use/server-tools). |
| CLI/UI success means a usable check completed | Corrected: unusable final results are errors with nonzero CLI exit; successful repair is accepted. Benchmarks still cache terminal refusals as scored-wrong observations. | [CLI tests](../tests/test_cli.py), [benchmark tests](../tests/test_bench.py). |
| Prompt preview is the exact execution prompt | Corrected/qualified: disabled extraction is respected; extracted-claim placeholders are illustrative because their runtime text is unknown. | [UI](../src/auto_fact_checker/ui.py), [UI tests](../tests/test_ui.py). |
| All consulted URLs are captured and leakage is excluded | Qualified: collect available structured search URLs and final citations; flag recorded URLs for known markers. Unreturned URLs, mirrors, memorization and shell access are not covered. | [Backend regressions](../tests/test_backend_integrity.py), [Codex event definitions](https://github.com/openai/codex/blob/main/codex-rs/exec/src/exec_events.rs), [benchmark source aggregation](../src/auto_fact_checker/bench/run.py). |
| Model catalog contains all models and invoice-accurate prices | Qualified: listed models and standard-rate estimates only; no account availability check. Published base/cache rates were checked on 2026-10-22. | [Catalog](../src/auto_fact_checker/catalog.py), [OpenAI pricing](https://developers.openai.com/api/docs/pricing), [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing). |
| Input counts and budgets include all known usage | Corrected: normalize Anthropic uncached input, cache reads and cache writes; apply context tiers per request. Missing cache-write TTL or interrupted usage produces unknown cost. Unknown charges remain visible. | [Cache accounting specification](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [backend regressions](../tests/test_backend_integrity.py). |
| Soft caps can overshoot only slightly, only in parallel | Corrected: recorded-cost admission checks cannot bound the cost of an admitted sequential or parallel call. Unknown charges are excluded; Claude's additional runtime budget is separate. | [Context](../src/auto_fact_checker/context.py), [spend logic](../src/auto_fact_checker/spend.py). |
| Logs contain full available prompts/outputs | Supported with limits: application prompts and returned text are untruncated; API text deltas and CLI event lines are logged as received. This does not expose hidden model reasoning or provider-internal prompts. | [Log tests](../tests/test_logs.py), [backend regressions](../tests/test_backend_integrity.py), [logging implementation](../src/auto_fact_checker/logs.py). |
| Agents are isolated from machine access | Qualified: they run without a sandbox, in temporary working directories, with selected configuration features disabled. This is not a security boundary. CLI versions found locally: Codex 0.163.0; Claude Code 2.1.302. No new live-auth/isolation test was run. | [Backend command construction](../src/auto_fact_checker/backends), local version/help output; [architecture limitations](../docs/architecture.md). |
| README screenshots demonstrate measured model quality | Corrected: refreshed screenshots use visibly marked synthetic fixtures, a zero-cost backend and separate runtime directories. Historical example results remain a separate dated observation. | [Screenshot script](../docs/scripts/take_screenshots.py), [offline fixture](../docs/scripts/offline_ui.py), [fixture guard test](../tests/test_offline_ui.py). |

## Experimental and statistical claims

| Claim and locations | Disposition and correction | Evidence |
|---|---|---|
| README/reports: SciFact A/B/C/D balanced accuracies 0.755/0.865/0.890/0.765 | Supported for the saved 200-item balanced binary subset. Generalization to other data/models is untested. | [Per-item results](results), [analysis](results/scifact_analysis.json), [analysis script](scripts/analyze_scifact.py). |
| Wilson intervals are balanced-accuracy intervals | Qualified: they are binomial accuracy intervals; the point estimates coincide on the exactly balanced sample. | [Benchmark design](../docs/benchmark.md), [statsmodels Wilson implementation](https://www.statsmodels.org/stable/generated/statsmodels.stats.proportion.proportion_confint.html). |
| Search alone explains all gains; rigorous prompts have no effect | Qualified: report paired estimates and intervals for the tested settings; nonsignificance is not equality or a universal causal conclusion. | [SciFact comparisons](results/scifact_analysis.json), [ASA statement](https://doi.org/10.1080/00031305.2016.1154108). |
| Naive is at least as good; repeated correction adds nothing | Qualified: describe observed means, runtime and uncertainty; no noninferiority margin/equivalence analysis was specified. | [Exp08 results](results/ai_errors_analysis.json), [Wilcoxon assumptions and null](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.wilcoxon.html). |
| 96–97% of errors were fully fixed after one pass | Corrected: weighted means are 0.958333/0.96875 with half-credit for partial fixes; full-correction counts are 44/48 and 45/48. These are judge-relative historical counts. | [Exp08 records](results/exp08_ai_errors), [metric tests](../tests/test_evidence.py). |
| A single retest estimates universal ±2–3 pp generator noise | Qualified: one pair gives 96.5% agreement and ΔBA 0.005 [−0.020,+0.031]; its item bootstrap does not estimate variance across independent complete runs. | [Retest records](results/exp01_retest), [analysis](results/scifact_analysis.json). |
| Preregistration preceded results | Supported for original design commits; later changes and new interpretations must remain labeled. | [Exp01 design](https://github.com/BurnyCoder/auto-fact-checker/commit/378c59b), [Exp07 design](https://github.com/BurnyCoder/auto-fact-checker/commit/f681d49), [Exp08 design](https://github.com/BurnyCoder/auto-fact-checker/commit/a2b7759). |
| Failure of a support rule falsifies the hypothesis | Qualified in dated clarifications: not meeting a support criterion does not establish absence; detectable effect size is not a confidence bound. Original rules remain attributable to their original commits. | [Design clarifications](../docs/benchmark.md), [correction design](../docs/correction_eval.md), [AI-error design](../docs/ai_error_bench.md). |
| Pilot accuracy was never analyzed | Corrected: the harness generated pilot metrics, but those items were excluded from the main evaluation. | [Pilot results](results/exp01_pilot/results.md), [main items](results/exp01/items.json). |
| Exp07 correctness 49% → 62% is a lower bound on truth | Qualified: these are results under supplied evidence and the judge's rubric; judge errors can bias either direction. | [Exp07](experiments/exp07_correction_loop.md), [gold-evidence prompt](../prompts/judge/gold_evidence.md). |
| Figure 3 uses n=100 throughout and plots returned answers | Corrected: n=100 at k=0,1; n=99 at k=2…8. It follows latest proposed corrections, including proposals not accepted by stopping; 50/99 differs from accepted-output 62/100. | [Trajectory code](scripts/analyze_correction.py), [missingness fixture](../tests/test_evidence.py). |
| Figure 2 black bars are medians | Corrected: even-sized samples previously used the upper middle observation. Bars now use the arithmetic mean of the middle pair. Primary numerical outputs are unchanged. | [Plot regression](../tests/test_evidence.py), [Python median definition](https://docs.python.org/3/library/statistics.html#statistics.median). |
| Historical Brier scores establish probability calibration | Qualified: calculations use `accuracy_pct/100` as a proxy; prompt scores are degrees of accuracy, and confidence calibration was not measured. | [Metrics](../src/auto_fact_checker/bench/metrics.py), [original JSON contract](../prompts/json_summary.md). |
| All 22 judge-flagged additions were verified true/hedges | Corrected: original annotations are retained; new item-level review has supported details, source conflicts, qualified inferences and unresolved claims. Neither classification establishes entire-text truth. | [22 item-level provenance records](results/exp08_claim_provenance_2026-10-22.json), [post-hoc output](results/exp08_posthoc.json). |
| Whole project cost was exactly $7.35 | Qualified: local ledger contains 2,953 entries, known billed estimates totaling $7.34726649, and one unknown-cost billed entry; last entry is dated 2026-10-17. Subscription fees and unrecorded charges are outside this total. | Local `logs/spend.jsonl`, read-only recomputation; ledger is not published, so the aggregate is locally verified only. |

## Dataset, source and example claims

| Claim and locations | Disposition and correction | Primary evidence |
|---|---|---|
| Frozen Exp08 originals are guaranteed true and all 48 edits are false | Corrected: originals are scoring references with documented defects; there are 48 annotated edits, including an ambiguous LSTM edit. | [Dated dataset errata](../benchmarks/ai_errors_v1/README.md), [frozen dataset](../benchmarks/ai_errors_v1/dataset.jsonl). |
| Self-attention without positional information is permutation-invariant | Corrected in errata: unmasked self-attention is permutation-equivariant, absent other position-dependent operations. Frozen text remains unchanged. | [Set Transformer §3.1](https://proceedings.mlr.press/v97/lee19d/lee19d.pdf). |
| LSTM “can last three timesteps” contradicts “can last thousands” | Ambiguous: no “only/at most” restriction is asserted. Exclude this annotation only in a labeled post-hoc sensitivity; retain original judgments and whole-text scores. | [Original LSTM paper](https://doi.org/10.1162/neco.1997.9.8.1735), [sensitivity implementation](scripts/exp08_posthoc.py). |
| AlexNet has uniquely verified 500,000 or 650,000 neurons | Unresolved source conflict: the proceedings abstract and PDF disagree. Both citations are preserved; no unique count is inferred. | [Abstract](https://papers.nips.cc/paper_files/paper/2012/hash/c399862d3b9d6b76c8436e924a68c45b-Abstract.html), [PDF](https://papers.nips.cc/paper_files/paper/2012/file/c399862d3b9d6b76c8436e924a68c45b-Paper.pdf). |
| SciFact only has binary truth and one evidence abstract | Corrected: the original task includes insufficient evidence; this project selects SUPPORT/CONTRADICT items and can attach multiple annotated abstracts. Five saved Exp07 claims have multiple abstracts. | [SciFact paper](https://aclanthology.org/2020.emnlp-main.609/), [saved Exp07 evidence](results/exp07_correction_codex/items.json). |
| Extraction implements Claimify | Qualified: a single prompt adopts stage names but retains opinions and selects an unresolved interpretation, unlike Claimify's filtering/disambiguation procedure. | [Claimify §§3.2–3.4](https://arxiv.org/html/2502.10855v2), [local template](../prompts/extract/claimify.md). |
| arXiv does not identify abstracts as metadata | Corrected: abstract is a required metadata field; arXiv applies CC0 to metadata. Full-paper licenses are separately specified. | [Metadata fields](https://info.arxiv.org/help/prep.html), [license policy](https://info.arxiv.org/help/license/index.html#metadata-license), [API summary field](https://info.arxiv.org/help/api/user-manual.html#summary-author-and-category). |
| BF16 halves all activation memory | Qualified: a BF16 element occupies half the bits of an FP32 element; mixed-precision execution can retain FP32 tensors/operations and other memory. | [Kalamkar et al.](https://arxiv.org/html/1905.12322v3), [example answer key](../docs/examples.md). |
| Representation studies establish general world models | Qualified: distinguish synthetic Othello-sequence experiments from spatial/temporal representations in Llama-2; neither demonstrates a complete general world model. | [Li et al.](https://arxiv.org/abs/2210.13382), [Gurnee & Tegmark](https://arxiv.org/abs/2310.02207). |
| Other planted-example corrections | Supported with the qualifications in the answer key; add direct sources for Stochastic Parrots and Chalmers rather than unsourced attribution. Original planted inputs and binary historical labels are preserved. | [Source-linked answer key](../docs/examples.md), [Bender et al.](https://doi.org/10.1145/3442188.3445922), [Chalmers 1995](https://consc.net/papers/facing.html). |

## Verification procedure and remaining limits

Regression tests were written for the identified runtime and metric defects before their fixes. The initial
baseline was 106 passing offline tests and nine excluded live tests. Backend regressions reproduce cancellation,
missing usage, structured-source capture and cache accounting with SDK-shaped fakes. UI validation uses an
explicit offline backend, including continuation and Stop through actual browser controls.

No new experiment demonstrates provider compatibility, factual accuracy, calibration, absence of contamination,
or secure agent isolation. Current provider documentation supports request construction; offline tests check
our handling of the documented shapes. Raw historical outputs may still contain false statements: preserving
them is necessary to reproduce what was observed. Dataset defects and unresolved source conflicts remain
visible rather than being silently repaired in those records.

Final checks on 2026-10-22:

| Check | Outcome |
|---|---|
| `uv run --no-sync pytest -q` | **143 passed, 9 live tests deselected**, 28.48 s. This includes all shipped CLI presets, failure/refusal behavior, cancellation, score parsing, usage accounting, source extraction, and evidence/metric regressions. |
| `uv pip check`; `uv tree --outdated --depth 1` | All installed packages compatible; no newer direct runtime/dev releases reported by the configured index. Updated Anthropic, OpenAI, pandas, json-repair and pydantic-settings, then reran the suite. Provider SDK signatures were inspected locally; paid compatibility calls were not made. |
| Actual CLI entry point with isolated fixture backends | Usable result: exit 0 and `done`; missing summary with repair disabled: exit 1 and `error`. The fixture returns visibly marked synthetic data and cannot invoke the real backends. |
| Offline Edge browser through `take_screenshots.py --offline --channel msedge` | Run, One more iteration, and Stop reached their expected terminal states. Refreshed all three UI screenshots and visually inspected them. |
| Full log inspection | Every saved prompt/output artifact from the offline fixture runs appears untruncated in its timestamped run log. The terminal capture includes complete prompt/output blocks. No real-ledger entries were added. |
| Evidence integrity | All 30 manifest entries match both their before-audit committed bytes and current working bytes. The three primary analysis JSON files are unchanged. |
| Derived artifacts | Recomputed the sensitivity/provenance output and corrected figures from existing records. Recompiled the nine-page Typst PDF and visually inspected every page, including tables, captions and bibliography. |
| Documentation links | Checked local targets across 72 Markdown documents and their local heading links: none missing. Of 69 public URLs checked, 65 returned HTTP 200; four DOI publisher destinations returned HTTP 403 to automated requests. Those DOI links are retained; reachability alone is not evidence of factual support. |
| Correctness/security/maintainability review | One integrated pass checked cancellation ownership, unusable-result handling, cache/usage accounting, frozen evidence, metric denominators, source provenance and artifact isolation. Corrected the additional even-sample median defect and remaining caption overstatements. No unresolved blocking issue was found in that review. |

Dependency checks are dated observations, not a promise of continuing currency. The repository retains its
modular pipeline and public configuration keys. All audited substantive claim groups above have a supported,
corrected, qualified or unresolved disposition. The unresolved statements and dataset limitations remain
explicit; this record does not certify arbitrary historical model prose as true.
