# All experiments — summary, glossary and results table

The detailed reports are in [`experiments/`](experiments), the paper in [`paper/`](paper), and the raw per-item data
in [`results/`](results). Every number here comes from `results/scifact_analysis.json`, the
`results/*/results.md` files, or the run records cited in each report.

## One-paragraph summary

- **System.** A configurable fact-checker where every block of a long "rigorous scientific fact-check" prompt is a
  UI toggle. It can run as one API call, as one agent (Codex / Claude Code), as an agent with subagents, or as
  separate calls per claim and per scientist.
- **Exp00.** On three AI-themed texts with planted errors, every preset agreed with a pre-written answer key on all
  32 claim verdicts. This is a functional check; the errors are textbook.
- **Exp01.** On a pre-registered SciFact benchmark (n = 200 balanced claims, `gpt-6-luna`), the full prompt with
  web search beat a simple single call: balanced accuracy **0.865 vs 0.755**, Δ = +0.110 [+0.062, +0.160],
  McNemar p = 2.7 × 10⁻⁵.
- **Exp02.** The pre-registered ablation shows that **web search alone explains the gain**:
  - the simple prompt with search reached 0.890 (Δ vs baseline +0.135)
  - the long rigorous prompt added nothing measurable on top of search (−0.025 [−0.061, +0.010], p = 0.27) while
    costing 29% more and producing 8.5× more output tokens
- **Noise.** Test–retest of the baseline agreed on 96.5% of predictions (Δ +0.005 [−0.020, +0.031]).
- **Exp03** (post hoc): the full prompt without search (0.765) does not beat the simple call either, so the
  prompt's verdict effect is null in both search conditions. It may improve ranking (AUROC +0.047
  [+0.013, +0.082]); this is exploratory.
- **Exp04** (post hoc): a Codex agent running the full prompt reached 0.876 on 40 claims, statistically
  indistinguishable from the single API calls.
- **Exp05** (post hoc): a Claude Code agent (Haiku) running the full prompt ranked claims best of all systems
  (AUROC 0.962) but was sceptical: SUPPORT recall 0.65, balanced accuracy 0.797 on the same 40 claims. It differs
  in model as well, and one bio-safety refusal was scored wrong.

- **Exp07** (pre-registered): is text the correct-until-labelled-accurate loop calls "correct" actually correct?
  Setup: a Codex agent with web search looped on 100 SciFact claims (≤ 20 passes), judged against the gold
  abstract by Claude Haiku (93% valid on originals).
  - It raised gold-correctness from **49% to 62%** (Δ +0.13 [+0.02, +0.24], p = 0.035).
  - It labelled **100%** of its answers correct while only **62%** [52, 71] were.
  - Passes after the first correction added nothing (61% → 62%).
  - It harmed 20% of originally correct claims; the sceptical checker rewrote 44 of 54 true claims.
  - Optional Claude Code subagent loop (n = 3, stopped early): it never labelled anything correct in 20 passes,
    while its final texts were judged correct. Neither loop's stopping signal tracks truth.

## Glossary (plain language)

| term | meaning |
|---|---|
| claim | one checkable statement, e.g. "GPT-3 has 175 billion parameters" |
| SciFact | a dataset of 1.4k expert-written biomedical claims labelled SUPPORT (true according to a paper) or CONTRADICT (false according to it); we use only those two labels |
| balanced accuracy | the average of "share of true claims called true" and "share of false claims called false"; 0.5 = coin flip, 1.0 = perfect, whatever the class balance |
| recall (per class) | of all claims of one class, the share the system labelled correctly |
| AUROC | probability that a random true claim gets a higher accuracy score than a random false claim (uses the full 0–100 score, not just the 50% cut-off) |
| Brier score | mean squared error of the predicted probability; lower is better (0 = perfect, 0.25 = always saying 50%) |
| Wilson CI | a 95% confidence interval for a proportion that behaves well near 0 and 1 |
| paired bootstrap CI | resample the same items for both systems 10,000 times; the middle 95% of the resampled differences is the interval |
| McNemar test | a test that looks only at items where the two systems disagree (b = only the first is right, c = only the second is right); exact version = binomial test on b vs c |
| pre-registered | hypothesis, metric, test and decision rule written down and committed before any data was collected |
| post hoc | decided after seeing data; exploratory, weaker evidence |
| test–retest | running the same system twice to measure how much results move by chance alone |
| leakage | the system finding the benchmark's answers (e.g. the dataset itself) online; mitigated by blocking dataset hosts and flagging any source URL that hits them |
| contamination | the benchmark being in the model's training data |
| confidence_pct | the model's self-reported confidence (0–100%) in each of its evaluations (uncertainty = 100 − confidence) |
| agent | an LLM that runs in a loop with tools (web search, shell) until it finishes, here Codex CLI or Claude Code |
| subagent | an agent started by another agent for a sub-task (e.g. one claim) |

## Systems ("configurations") and results

All systems use `gpt-6-luna` (OpenAI, $0.10/$0.50 per 1M tokens; web search $0.01 per call) with reasoning effort
low. Each takes one claim as input and returns a 0–100 accuracy score; the prediction is SUPPORT iff the score is
≥ 50.

| id | architecture | prompt | search | data | n | balanced accuracy | AUROC | Brier | cost | status |
|---|---|---|---|---|---|---|---|---|---|---|
| A | 1 API call | minimal ("Fact-check the following text." + JSON) | none | SciFact binary | 200 | 0.755 | 0.844 | 0.165 | $0.06 | pre-registered (Exp01) |
| A′ | same as A, re-run | minimal | none | same items | 200 | 0.760 | – | – | $0.06 | pre-registered noise control |
| B | 1 API call | full rigorous (24 blocks; 45 labels + 12 conditions scored with confidence) | hosted web_search ≤3 calls, dataset hosts blocked | same | 200 | 0.865 | 0.944 | 0.101 | $2.97 | pre-registered (Exp01) |
| C | 1 API call | minimal | as B | same | 200 | 0.890 | 0.956 | 0.087 | $2.30 | pre-registered secondary (Exp02) |
| D | 1 API call | full rigorous | none | same | 200 | 0.765 | 0.891 | 0.142 | $0.44 | post hoc (Exp03) |
| E | Codex CLI agent | full rigorous | live web search (≤3 stated in prompt) | first 40 of the same items | 40 | 0.876 | 0.917 | 0.113 | $0 billed ($0.91 notional) | post hoc (Exp04) |
| F | Claude Code agent, **claude-haiku-5-5** | full rigorous | WebSearch/WebFetch (≤3 stated in prompt) | same 40 items | 40 | 0.797 | 0.962 | 0.161 | $0 billed ($1.27 notional) | post hoc (Exp05) |

| comparison | n | Δ balanced accuracy [95% CI] | McNemar b / c, p | Δ AUROC [95% CI] | reading |
|---|---|---|---|---|---|
| B − A | 200 | +0.110 [+0.062, +0.160] | 3 / 25, 2.7 × 10⁻⁵ | +0.099 [+0.052, +0.150] | H1 supported (pre-registered primary) |
| C − A | 200 | +0.135 [+0.086, +0.186] | 2 / 29, 4.6 × 10⁻⁷ | +0.112 [+0.065, +0.163] | search alone helps (pre-registered) |
| B − C | 200 | −0.025 [−0.061, +0.010] | 9 / 4, 0.27 | −0.012 [−0.032, +0.004] | no detectable benefit of the rigorous prompt given search (pre-registered) |
| A′ − A | 200 | +0.005 [−0.020, +0.031] | 3 / 4, 1.0 | – | noise floor (pre-registered) |
| D − A | 200 | +0.010 [−0.026, +0.047] | 6 / 8, 0.79 | +0.047 [+0.013, +0.082] | prompt without search: no verdict gain, maybe better ranking (post hoc) |
| B − D | 200 | +0.100 [+0.055, +0.148] | 2 / 22, 3.6 × 10⁻⁵ | +0.053 [+0.021, +0.089] | search helps under the full prompt too (post hoc) |
| E − A / B / C | 40 | +0.051 / −0.029 / −0.059, every CI spans 0 | 2/4 · 2/1 · 3/1 | – | Codex agent indistinguishable at n = 40 (post hoc) |
| F − A / B / C / E | 40 | −0.028 / −0.109 / −0.138 [−0.250, −0.045] / −0.079 | 6/4 · 7/2 · 6/0 (p = 0.031) · 7/3 | +0.073 / −0.017 / −0.031 / +0.045 | Claude agent: sceptical, best ranking; vs C nominal only (1 of 12 post-hoc tests; model confound) |

## Correction loop (Exp07, pre-registered)

| loop | n | judge-correct: original → answer | self-labelled correct | precision of the self-label | extra passes (first correction → answer) | repair / harm | billed |
|---|---|---|---|---|---|---|---|
| Codex agent + web search (gpt-6-luna), ≤ 20 passes | 100 | 49% → 62% (Δ +0.13 [+0.02, +0.24], p = 0.035) | 100% | 62% [52, 71] | 61% → 62% (Δ +0.01 [−0.06, +0.08]) | 52% / 20% | $0.18 |
| Claude Code lead + subagents (Haiku), ≤ 20 passes (exploratory, stopped early) | 3 | 0/3 → 2/3 (Luna judge) | 0% (two claims ran 20 passes; one refusal) | – | – | – | $0.03 |

The primary judge is Claude Haiku with the gold abstract (93% valid on originals). With Luna as judge (post hoc)
the conclusions are the same: self-label precision 61%, extra passes Δ 0.00.

## Qualitative runs (Exp00)

Nine runs covered presets L0–L5, iteration, Claude/Codex agents and subagents. They made 49 calls in total and
agreed with the answer key on all 32 claims (details and costs: [exp00](experiments/exp00_ai_texts.md)).

## What was learned across experiments

- **Retrieval matters more than prompt length for binary verification.** The gains come from CONTRADICT claims
  (recall 0.72 → 0.88–0.93), which the model accepts as plausible without evidence.
- **More instructions are not free.** The rigorous prompt costs 8.5× the output tokens and gave no measurable
  verdict accuracy on SciFact. Its value, if any, is in the qualitative output (labels, conditions, corrections),
  which SciFact does not score.
- **Synthesis of many perspectives moderates scores** toward the middle (Exp00, L5).
- **Self-assessed stopping is not verification** (Exp07). The loop marks everything correct after 1–2 passes.
  About a third of those texts are wrong by gold evidence, and further passes rewrite rather than repair (hedging,
  question drift).
- **Ranking and threshold can disagree.** The Claude agent had the best AUROC but a poor 50% cut-off (Exp05).
  The prompt without search raised AUROC without raising accuracy (Exp03). The threshold metric alone hides this.
- **Delegation can be fabricated.** In 4 smoke tests Codex never spawned a sub-agent, and twice it claimed one had
  answered (Exp00).
- **Refusals are a failure mode of their own.** Anthropic's bio-safety filter refused some biomedical claims,
  non-deterministically, and the JSON repair step once turned a refusal into a fabricated verdict (fixed, Exp05).
- **Engineering findings** (Exp00): workspace header, direct search mode, CLAUDE.md isolation, Codex AGENTS.md
  limitation, the subagent-delegation prompt. See the table in [exp00](experiments/exp00_ai_texts.md).

## Spend

The whole project (implementation tests, live tests, example runs, UI checks and all experiments) is recorded
call by call in `logs/spend.jsonl`. **Billed total: $6.90 of the $10 cap.** Agent runs on subscription auth are
not billed; their notional cost is logged separately.
