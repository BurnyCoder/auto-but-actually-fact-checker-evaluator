#set document(title: "Search and prompt length in LLM fact-checking: SciFact and correction experiments", author: "Libor Burian")
#set page(paper: "a4", margin: (x: 2cm, y: 2.2cm), numbering: "1")
#set text(size: 10pt)
#set par(justify: true)
#set heading(numbering: "1.")
#show link: underline

#align(center)[
  #text(15pt, weight: "bold")[Search and prompt length in LLM fact-checking: SciFact and correction experiments]
  #v(4pt)
  Libor Burian — independent researcher
  #v(2pt)
  #text(9pt)[October 2026 · code and result records: #link("https://github.com/BurnyCoder/auto-but-actually-fact-checker-evaluator")]
]

#block(inset: (x: 1.2cm))[
  *Abstract.* We turn a long, hand-written "rigorous scientific fact-check" prompt into a configurable system in
  which each sentence and each list of the prompt is a toggle. The prompt requests 0–100% assessments and
  self-reported confidence for selected verdict labels and evaluative conditions; responses can omit fields.
  Execution ranges from one non-agentic API call to Codex / Claude Code agents with subagents and separate calls
  per claim and per scientist persona. In a pre-registered evaluation on 200 balanced binary SciFact claims with
  `gpt-6-luna`, the full prompt with hosted web search beat a minimal single call: balanced accuracy 0.865 vs
  0.755, Δ = +0.110 [95% CI +0.062, +0.160], exact McNemar p = 2.7×10⁻⁵. A pre-registered ablation found a gain
  from search with the minimal prompt, which reached 0.890. The rigorous prompt added no
  detectable accuracy given search (Δ = −0.025 [−0.061, +0.010], p = 0.27) while producing 8.5× more output tokens.
  Post hoc, the full prompt without search had no detectable verdict gain (0.765 vs 0.755), although its AUROC was higher (+0.047 [+0.013, +0.082]). A correction-loop evaluation raised judge-assessed correctness from 49% to 62%, while the loop labelled every answer correct. On 20 AI-research passages with 48 annotated edits, one pass fully corrected 44/48 or 45/48 edits per the judge; half-credit weighted scores were 0.958–0.969. Three further passes had no detectable mean-score gain (rigorous Δ +0.45 [−4.6, +4.8]) and reduced the rigorous arm's per-passage fix rate (−0.067 [−0.117, −0.022]). The naive arm had a higher observed mean at one sixth of the runtime; equivalence was not established. A dated reassessment identifies one ambiguous injected edit and unresolved source claims. All verdict and corrector systems use `gpt-6-luna` except the Claude Haiku agent arms; the
  benchmarks are short SciFact claims and 20 AI-research passages.
]

= Introduction

LLM fact-checking pipelines usually split text into claims, retrieve evidence and verify each claim
@safe @factscore @factool @veriscore. Practitioners also write long "be rigorous" prompts that enumerate failure
modes (overgeneralization, cherry-picking, category errors), epistemic stances (Bayesian, frequentist,
empiricist) and exemplary scientists. Such prompts are hard to evaluate because they bundle many interventions.
Our contributions:

1. A system that makes each component of such a prompt independently switchable. Its output contract requests
   scores and confidence for selected evaluative components. The execution strategy (API call vs agent, subagents,
   per-claim and per-persona calls, iteration) is configurable per pipeline step (§2).
2. A pre-registered paired evaluation on SciFact @scifact that separates the effect of the prompt from the effect
   of web search, with one paired baseline retest (§3–4).
3. Two pre-registered tests of iterative self-correction. One judges corrections against gold evidence (SciFact);
   the other uses a new benchmark of real AI-research passages with annotated injected edits, scored on a 0–100
   spectrum pass by pass (§4).

= System

*Prompt as blocks.* The original prompt (Appendix A) is split into 20 sections, verbatim except for light rewording
where a sentence was cut, for example "Evaluate it from both bayesian and frequentist perspectives." Four added
sections (a NeurIPS-reviewer role, claim classification, 0–100% scoring and confidence) make 24 toggles. The lists
(45 verdict labels, degrees fully / partially / slightly, 10 style adjectives, 63 scientists, 15 claim types) are
editable. A test asserts that the all-on prompt contains every list item of the original and every sentence kept
verbatim.

*Output contract.* The prompt requests a final JSON block containing, per claim:
- accuracy and confidence
- claim types with confidences
- every selected label with a degree, score and confidence
- up to 12 conditions with a specified interpretation; the Bayesian-style score is a subjective assessment,
  without a specified prior/likelihood calculation or established posterior calibration
- a corrected claim

The JSON also requests corrected text and a list of issues. Claim types, confidences, labels and conditions are
requested only while their sections are enabled; accuracy, corrections and issues always are. Parsing tolerates
common JSON defects and missing fields; a repair step attempts to recover an unusable summary. Neither parsing
nor repair verifies the factual content. Scores and confidence are model-reported assessments.

*Execution.* A run has five configurable steps: extract (a single-call adaptation inspired by Claimify @claimify), check, perspective,
synthesize and repair (repair runs only when an answer lacks the JSON). Each step independently chooses:
- API call (OpenAI Responses / Anthropic Messages with server-side web search) or agent (Codex CLI / Claude Code)
- model, reasoning effort, search on/off and its caps
- subagents, prompt template and prompt override

Claims can be checked as a whole text, by agent subagents, or by separate calls; scientist personas likewise.
The adaptation retains opinions and chooses a likely reading of unresolved ambiguity, unlike Claimify's filtering
and disambiguation stages. "Iterate until accurate" re-checks corrected text until model-reported scores for all
returned claims reach a threshold or another stopping condition applies. Every call passes
through one context that logs full prompts and outputs and checks recorded-cost budgets. These checks are soft:
costs are recorded after calls, sequential or parallel calls can overshoot, and unknown costs are omitted from totals.

= Evaluation design (pre-registered)

The design (#link("https://github.com/BurnyCoder/auto-but-actually-fact-checker-evaluator/blob/main/docs/benchmark.md")[docs/benchmark.md])
was committed before any paid call.

*Data.* SciFact @scifact claims whose evidence labels are all SUPPORT or all CONTRADICT; NEI and conflicting
claims are dropped. The pool is the validation and train splits; nothing was tuned on it. The sample is balanced,
n = 200, seed 0, excluding the 6 pilot claims used to estimate cost. Pilot accuracy was computed by the harness
but excluded from the main evaluation.

*Prediction rule.* p = overall accuracy / 100; SUPPORT iff p ≥ 0.5. Unparseable outputs count as wrong.

*Systems* (all `gpt-6-luna`, effort low, one call per claim):
- A: minimal prompt, no search
- B: full default prompt, with hosted web search capped at 3 tool calls and dataset hosts blocked
- C: minimal prompt with B's search

*Metrics.* Primary: balanced accuracy, compared with an exact McNemar test @mcnemar @dietterich and a 95%
paired-bootstrap CI over 10,000 resamples @bergkirkpatrick @efron. Secondary: accuracy with Wilson CI @wilson, macro-F1, AUROC,
Brier score. Historical Brier calculations use accuracy scores divided by 100 as probability proxies; those
degree-of-accuracy scores are not established calibrated probabilities, and confidence calibration was not tested.

*Hypotheses.* H1: BA(B) > BA(A). It is supported only if Δ > 0, the CI excludes 0 and p < 0.05. H2 (secondary):
C − A isolates search; B − C isolates the prompt given search.

*Sample size.* The pre-registered rule (largest balanced n within about \$5 at the pilot's measured cost) was
applied conservatively at the pilot's worst-case cost (≈ 208) and rounded down to n = 200. It exceeds the n ≈ 155
that Connor's approximation @connor gives for δ = 10 pp at 20% discordance (two-sided α = 0.05, 80% power).

*Leakage control.* The API search configuration requested dataset-host exclusions. Returned source URLs were
logged and flagged when they matched a dataset host or "scifact"; unreturned browsing activity is not observed.

= Results

#figure(image("../figures/fig1_balanced_accuracy.png", width: 92%),
  caption: [Balanced accuracy with 95% percentile-bootstrap CIs over items (n per system shown).])

#figure(
  table(columns: 8, align: (left, right, right, right, right, right, right, right), stroke: 0.4pt,
    [*system*], [*n*], [*bal. acc.*], [*acc. [Wilson 95%]*], [*recall S / C*], [*AUROC*], [*Brier*], [*cost \$*],
    [A minimal], [200], [0.755], [0.755 [0.691, 0.809]], [0.79 / 0.72], [0.844], [0.165], [0.06],
    [B full + search], [200], [0.865], [0.865 [0.811, 0.906]], [0.85 / 0.88], [0.944], [0.101], [2.97],
    [C minimal + search], [200], [0.890], [0.890 [0.839, 0.926]], [0.85 / 0.93], [0.956], [0.087], [2.30],
    [D full, no search#super[†]], [200], [0.765], [0.765 [0.702, 0.818]], [0.75 / 0.78], [0.891], [0.142], [0.44],
    [E Codex agent, full#super[†]], [40], [0.876], [0.875 [0.739, 0.945]], [0.87 / 0.88], [0.917], [0.113], [0 (subscr.)],
    [F Claude Code agent (Haiku), full#super[†]], [40], [0.797], [0.775 [0.625, 0.877]], [0.65 / 0.94], [0.962], [0.161], [0 (subscr.)],
  ),
  caption: [Per-system results; recall S / C = SUPPORT / CONTRADICT recall. #super[†] post hoc. No leak flags occurred in A–E; F had one benign flag (a paperswithcode author page); D had one transient API failure, re-run once.])

#figure(
  table(columns: 4, align: (left, right, right, left), stroke: 0.4pt,
    [*comparison*], [*Δ bal. acc. [95% CI]*], [*McNemar b / c, p*], [*status*],
    [B − A], [+0.110 [+0.062, +0.160]], [3 / 25, 2.7×10⁻⁵], [pre-registered primary: H1 supported],
    [C − A], [+0.135 [+0.086, +0.186]], [2 / 29, 4.6×10⁻⁷], [pre-registered secondary],
    [B − C], [−0.025 [−0.061, +0.010]], [9 / 4, 0.27], [pre-registered secondary],
    [A′ − A (re-run)], [+0.005 [−0.020, +0.031]], [3 / 4, 1.0], [noise control],
    [D − A], [+0.010 [−0.026, +0.047]], [6 / 8, 0.79], [post hoc],
    [B − D], [+0.100 [+0.055, +0.148]], [2 / 22, 3.6×10⁻⁵], [post hoc],
    [E − C (n = 40)], [−0.059 [−0.167, +0.034]], [3 / 1, 0.62], [post hoc],
    [F − C (n = 40)], [−0.138 [−0.250, −0.045]], [6 / 0, 0.031], [post hoc; model differs],
  ),
  caption: [Paired comparisons on shared items. In "X − Y", b = only Y (the subtracted system) correct, c = only X correct.])

*H1 is supported.* The improvement is concentrated in CONTRADICT claims (recall 0.72 → 0.88). Without search,
A assigns many of these claims accuracy scores of 65–95% (Fig. 2); these outputs do not establish the model's
reason for the errors.

*Search improves the observed verdict scores.* C − A (+0.135) exceeds the observed B − A gain, while no
positive B − C difference was detected.
The 95% interval for B − C has an upper endpoint of about +1 pp. B produced 3,562 output
tokens per claim on average, vs 420 for C. Post hoc, D had no detectable verdict advantage over A (Δ +0.010 [−0.026, +0.047]); its higher AUROC (+0.047 [+0.013, +0.082]) is a hypothesis for future work. Codex agent E reached 0.876 on 40 claims, with no detected balanced-accuracy difference from the API systems and no equivalence test. Claude Code agent F (Haiku) ranked claims well (AUROC 0.962, versus B's 0.978 and C's 0.992 on the same 40 claims) but had SUPPORT recall 0.65. Its lower balanced accuracy versus C (p = 0.031) is one of 18 post-hoc tests and confounded by the model.

*Retest.* A re-run of A agreed on 96.5% of predictions, with ΔBA +0.005 [−0.020,+0.031]. This is an
item-bootstrap interval for one pair of runs, not an estimate of variance across independently repeated runs.

#figure(image("../figures/fig2_scores_by_gold_label.png", width: 100%),
  caption: [Model-reported accuracy by gold label for the 200-item systems (black bar: median).])

*Qualitative validation.* On three AI research / philosophy / engineering texts with planted errors (answer key
with sources in the repository), eight runs covered all execution presets: single call, Codex and Claude agents,
Claude subagents, per-claim agents, per-claim × per-scientist calls, and iteration. Together they agreed with the
key on all 42 claim verdicts, with complete JSON contracts (a ninth run tested subagent delegation on a 2-claim
text). The errors are textbook, so this demonstrates function,
not accuracy. Two observations:
- In the run merging three scientist personas, scores were closer to 50%. For example, "the Turing test is widely
  accepted as a sufficient test for consciousness" scored 46% after synthesis vs 5–25% in single runs. This
  observation does not isolate the effect of synthesis.
- One correction pass raised a text's self-assessed accuracy from 18% to 95%. Because the same model grades its
  own correction, this measures self-consistency, not truth.

*Is "labelled correct" correct? (Exp07, pre-registered.)* We also tested the iterate-until-accurate loop. A Codex
agent (`gpt-6-luna`, live web search) corrected and re-checked 100 SciFact claims until it rated every claim
≥ 90%, with at most 20 passes. A cross-family judge (`claude-haiku-5-5`, 93% accurate on the original claims)
compared each text with the supplied gold-evidence abstracts. Correct means the central claim is entailed, nothing is contradicted,
and the text addresses the same question.
- Gold-correctness rose from 49% to 62% (Δ +0.13 [+0.02, +0.24], McNemar 10 / 23, p = 0.035).
- The loop labelled all 100 answers correct; the judge rated 62% [52, 71] correct.
- No improvement was detected after the first correction (61% → 62%, Δ CI [−0.06,+0.08]).
- 20% of originally correct texts became incorrect: the checker rated 44 of 54 true claims below 90% and rewrote
  them into hedged or narrower statements.

With Luna as judge (post hoc) the self-label precision is 61% and extra passes add 0.00. An exploratory Claude Code
loop with claim and scientist subagents failed in the opposite direction. On 2 of 3 claims it ran all 20 passes
without ever labelling its text correct, although both judges found its final texts correct; the third claim was
refused. A self-assessed stopping rule does not track gold correctness (Fig. 3).

*Post hoc, on the same 100 claims.*
- *Verdicts.* The agent's first-pass verdict reaches 0.921 balanced accuracy. That compares with 0.774 / 0.779
  without evidence (A / D), 0.903 / 0.923 with API search (B / C), and 0.934 for a judge given the cited paper.
- *Corrections.* The judge rated 62% of returned texts correct. Relative to the dataset labels, the agent detects
  93% of false claims; the judge accepts about half of their returned texts.
- *One pass vs. the loop.* A single agent pass (keep the original if rated ≥ 90%, else use its correction) already
  reaches 62% (from 49%). The full loop adds +0.00 [−0.06, +0.06] at 2.5× the cost; the two answers are identical on
  76 of 100 claims.
- Swapping the judge to Luna gives the same picture: 37% → 62% → 61%.

#figure(
  table(columns: 4, align: (left, right, right, right), stroke: 0.4pt,
    [*Exp07 claims (n = 100)*], [*original*], [*single agent pass*], [*full loop*],
    [texts correct (Haiku judge)], [49%], [62%], [62%],
    [texts correct (Luna judge)], [37%], [62%], [61%],
    [notional cost / time per claim], [–], [\$0.023 / 34 s], [\$0.059 / 100 s],
  ),
  caption: [Post hoc: correction accuracy of one agent pass vs. the iterate-until-accurate loop on the same claims.])

#figure(image("../figures/fig3_correction_loop.png", width: 72%),
  caption: [Exp07: the loop's rating versus judge correctness of its latest proposed text. Proposals carry forward after stopping; judged n = 100 at k = 0,1 and 99 at k = 2–8 because one judgment is missing. These proposals can differ from returned answers, whose correctness is 62/100. Self-ratings cover only active items (n = 100,90,24,9,4,3,1,1).])

*Obviously wrong AI-research text (Exp08, pre-registered).* We built a benchmark
(#link("https://github.com/BurnyCoder/auto-but-actually-fact-checker-evaluator/tree/main/benchmarks/ai_errors_v1")[ai_errors_v1]) in the
spirit of synthetic perturbation @factcc.
- *Passages:* 10 Wikipedia leads and 10 arXiv abstracts about AI research, with k ∈ {0, …, 5} injected one-fact
  edits intended as errors (48 in total, e.g. 2012 → 2022, 28.4 → 284 BLEU) and 4 no-injection controls.
- *Injection:* `gpt-6-luna` proposed the edits; code validated them; the AI coding agent that built the repository
  checked every edit individually (4 of 48 repaired, 2 relabelled).
- *Arms:* a Codex agent with web search was forced through 4 correction passes with either the naive
  ("Fact-check the following text.") or the full rigorous prompt.
- *Judge:* `claude-haiku-5-5`, given the original passage, the injected errors and the candidate. It scored each
  error (corrected 1, partially 0.5, uncorrected 0) and the whole text (0–100).
- *Validity:* original passages scored 99.1, and the corrupted-input score fell with k (Spearman ρ = −0.81).

#figure(
  table(columns: 3, align: (left, right, right), stroke: 0.4pt,
    [*n = 20 passages, 48 edits*], [*naive prompt*], [*rigorous prompt*],
    [score: corrupted → pass 1 → pass 4], [38.6 → 90.4 → 89.4], [40.0 → 85.7 → 86.2],
    [pass 4 − pass 1 (95% CI)], [−1.0 [−6.8, +5.3]], [+0.45 [−4.6, +4.8]],
    [weighted fix score, pass 1 → pass 4], [0.958 → 0.969], [0.969 → 0.896],
    [fully corrected edits, pass 1], [44/48 (91.7%)], [45/48 (93.8%)],
    [words (corrupted input 157), pass 1 → pass 4], [151 → 191], [176 → 254],
    [time / output tokens per pass], [18 s / 1.5k], [110 s / 18k],
  ),
  caption: [Exp08: one correction pass vs. four (primary judge `claude-haiku-5-5`, scored against the original passage).])

*Results.*
- *One pass* raised the score by +51.8 [+34.1, +68.9] (naive) and +45.8 [+28.8, +61.9] (rigorous), Wilcoxon
  signed-rank @wilcoxon p < 0.001.
- *Passes 2–4* had no detectable mean-score effect in either arm or under either judge; the intervals permit
  both improvement and harm.
- *Erosion under the rigorous prompt:* the per-passage fix rate fell by 0.067 [0.022, 0.117] (6 of 16 passages
  worse, none better, p = 0.015). In the saved judgments, none of the fully corrected annotations became
  uncorrected; 7 lost full credit through hedging or deletion. At pass 4, mean passage length was 61% above
  the original reference length (254 vs 157 words), and the loop's mean self-rating stayed near 96%.
- *Prompt:* the rigorous prompt scored lower than the naive one after pass 1 (−4.65 [−10.2, +1.8], 16 of 20
  passages worse, Wilcoxon p = 0.017).
- *Clean controls* were rewritten in every pass by both arms.
- *Reassessment (post hoc, 2026-10-22, by an AI coding agent).* The 22 pass-1 flags include 10 supported
  details, 3 source conflicts, 5 qualified inferences and 4 unresolved statements. AlexNet's neuron count and
  Transformer BLEU figures conflict within primary sources; citation does not settle those numbers. The
  Transformer reference also incorrectly calls self-attention invariant rather than equivariant
  @settransformer. Item-level evidence and the superseded historical annotations are retained in the repository.
- *Dataset ambiguity.* LSTM edit 3 changes "can last thousands" to "can last three" timesteps, without "only";
  this does not establish a false claim @lstm. Excluding that edit post hoc gives weighted scores of
  0.968 → 0.979 (naive) and 0.979 → 0.904 (rigorous) over 47 edits. No text or whole-text judge score was changed.

#figure(image("../figures/fig4_ai_errors_passes.png", width: 92%),
  caption: [Exp08: reference-judge score and weighted edit-fix score after each forced pass, with 95% bootstrap bands (20 passages, 48 historical annotations; partial fixes receive half credit). Pass 0 is the corrupted input.])

= Related work

Decompose–retrieve–verify pipelines include FActScore @factscore, SAFE @safe, FacTool @factool,
VeriScore @veriscore and FIRE @fire; Factcheck-Bench @factcheckbench and OpenFactCheck @openfactcheck benchmark
such checkers. Claimify @claimify studies claim extraction. Our system reuses this decomposition but focuses on
making a monolithic expert prompt modular and auditable. Our tested search-enabled configurations scored higher
on SciFact, consistent with those pipelines' use of retrieved evidence. No claim of literature-wide novelty is made.
Iterative self-refinement @selfrefine improves many generation
tasks, but intrinsic self-correction without external feedback often fails or degrades answers @selfcorrect.
Exp07–08 observed most improvement after the first correction with search, with no detectable extra mean-score
gain from further passes in these samples. Synthetic perturbations follow FactCC @factcc but still require
validation of both the original reference and the proposed errors.

= Limitations

- *Limited models and settings.* Most correctors use `gpt-6-luna` at low effort; Claude agent arms and the primary
  correction judge use Haiku, with Luna as a secondary judge. Other models or efforts may use the rigorous
  instructions differently.
- *Project's SciFact subset: short single claims.* This evaluation selects binary evidence labels. The prompt's distinctive outputs
  (label scores, condition assessments with confidences, corrections) were not evaluated against human judgments,
  and the calibration of the self-reported confidences was not measured.
- *Contamination and gold semantics.* SciFact may occur in undisclosed pretraining data; its labels are relative
  to supplied evidence abstracts, sometimes more than one. Reference and judge errors prevent a demonstrated
  lower bound on real-world correctness.
- *Leakage.* Host blocking and URL flagging (0 flags except one benign flag in F and one benign flag, an iGEM
  wiki page on github.com, in the exploratory Exp07 Claude arm) cannot exclude unknown mirrors.
- *Post-hoc arms* (D, E, F) are exploratory. E and F have n = 40 and are underpowered.
- *Agent isolation.* With subscription authentication, Codex agents still load the user's global AGENTS.md; only a
  counter-instruction is applied.
- *Exp08 scope.* 20 passages (planned 80% power only around d_z ≳ 0.65), with synthetic edits in famous, possibly
  memorised sources whose originals the agent can find online. The same model family injected and corrected the
  errors, and the reference-based judge sometimes penalises supported additions. The QC of the injected errors and the audit of
  judge-flagged statements were done by an AI coding agent, not by a human expert.
- *Delegation and refusals.* In four smoke tests, Codex (`gpt-6-luna`) never actually spawned a sub-agent and
  twice reported a fabricated sub-agent answer. Claude Haiku refused some biomedical claims non-deterministically
  (bio-safety filter); one refusal is scored wrong in F.
- *Statistical interpretation.* Nonsignificance does not establish equality, and the power calculation is not
  an effect-size bound @asa. Exp08's Wilcoxon test concerns the paired-difference distribution; its bootstrap
  interval concerns the mean. No noninferiority analysis was specified. Historical decision rules are preserved
  with dated clarifications linked from the experiment reports.

= Conclusion

For the tested model and SciFact sample, adding search improved verdict scores; no positive verdict gain from
the rigorous prompt was detected. The loop accepted every returned answer although 38% failed the gold-evidence
judge. Further passes had no detectable correctness gain in Exp07 or mean-score gain in Exp08; the rigorous
Exp08 arm lost weighted edit-fix score. These findings do not establish equivalence, general recommendations
across tasks, or the correctness of the judges themselves. Validation of labels, conditions and confidence
scores requires independent annotated evidence.

*Cost and reproducibility.* As of 2026-10-22, the local ledger contained \$7.34726649 in known billed estimates
across 2,953 entries (\$7.55085675 across 3,004 entries by 2026-10-28), with one billed entry of unknown cost; this
is not a provider-invoice total and excludes subscription fees. OpenAI cache writes were not priced before
2026-10-28, which understates the historical OpenAI API estimates by at most \$0.17.
Commands, configurations, result records, analysis scripts and preregistrations are published. Raw `runs/` and
`logs/` are ignored by Git; some timing, cost and Exp00 checks require those local artifacts. The dated
#link("https://github.com/BurnyCoder/auto-but-actually-fact-checker-evaluator/blob/main/reports/verification_2026-10-28.md")[verification record]
documents an independent recomputation of every reported number and the remaining limitations. Raw evidence and
primary numerical results were preserved during the 2026-10-22 and 2026-10-28 corrections.

#bibliography("refs.yml", style: "ieee")

#pagebreak()
= Appendix A: original prompt (verbatim, abridged lists)

#text(8.5pt)[Fact-check every distinct factual claim in the following text. For each claim, research it in depth
scientifically by searching the web and using reputable scientific sources as much as possible to verify it, then
write a detailed analysis, report whether it's fully, partially, slightly: accurate, inaccurate, misleading,
oversimplified, … (45 labels) … Note any important nuance, context and complexity that's omitted. Be as
scientific, pedantic, sceptical, direct, logical, technical, academic, rigorous, steelmanning, in good faith, etc.,
as possible. Classify strengths and weaknesses, advantages and disadvantages, limitations and potentials, ups and
downs, good and bad. Evaluate it from both empiricist and rational perspectives. Evaluate it from both bayesian and
frequentist perspectives. Do not just agree, do not be sycophantic, you can be blunt, do not sugarcoat things.
Maximize predictive power and explanatory power. I want accuracy and precision. You are the most rigorous
scientist, think like and apply scientific rigor like Karl Popper, … (63 names) … Synthesize as many scientific
perspectives, empirical fact checks, scientific analyses, etc. as possible. Double check yourself as well. Search
the web a lot. Think a lot. Quote the specific claims and provide your findings with sources you relied on. Quote
directly from sources in your findings. Write a corrected version of each claim after each claim, and corrected
version of the whole text at the end. Write a list of all issues in the overall text, that you found, in one
sentence, at the end.]

= Appendix B: configurations

System configurations are JSON files in `configs/bench/`:
- A = `baseline.json`
- B = `full_single_openai.json`
- C = `baseline_search.json`
- D = `full_no_search.json`
- E = `full_agent_codex.json`
- F = `full_agent_claude.json`

The defaults are in `src/auto_fact_checker/config.py`. Blocked hosts: huggingface.co, github.com,
githubusercontent.com, kaggle.com, paperswithcode.com, allenai.org.

= AI statement

Claude Code (Anthropic's AI coding agent) wrote this codebase and this paper, executing an exact specification
provided by a human (Libor Burian). Human cleanup and rewriting of the code and text are in progress.
