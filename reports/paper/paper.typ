#set document(title: "Search, not prompt length: a configurable rigorous LLM fact-checker evaluated on SciFact", author: "Libor Burian")
#set page(paper: "a4", margin: (x: 2cm, y: 2.2cm), numbering: "1")
#set text(size: 10pt)
#set par(justify: true)
#set heading(numbering: "1.")
#show link: underline

#align(center)[
  #text(15pt, weight: "bold")[Search, not prompt length: a configurable rigorous LLM fact-checker evaluated on SciFact]
  #v(4pt)
  Libor Burian — independent researcher
  #v(2pt)
  #text(9pt)[October 2026 · code, data and logs: #link("https://github.com/BurnyCoder/auto-fact-checker")]
]

#block(inset: (x: 1.2cm))[
  *Abstract.* We turn a long, hand-written "rigorous scientific fact-check" prompt into a configurable system in
  which each sentence and each list of the prompt is a toggle. Every evaluative condition (45 verdict labels and
  12 conditions such as Bayesian or empiricist assessment) is scored 0–100% with a self-reported confidence.
  Execution ranges from one non-agentic API call to Codex / Claude Code agents with subagents and separate calls
  per claim and per scientist persona. In a pre-registered evaluation on 200 balanced binary SciFact claims with
  `gpt-6-luna`, the full prompt with hosted web search beat a minimal single call: balanced accuracy 0.865 vs
  0.755, Δ = +0.110 [95% CI +0.062, +0.160], exact McNemar p = 2.7×10⁻⁵. A pre-registered ablation attributes the
  whole gain to retrieval: the minimal prompt with the same search reached 0.890. The rigorous prompt added no
  detectable accuracy given search (Δ = −0.025 [−0.061, +0.010], p = 0.27) while producing 8.5× more output tokens.
  In post-hoc arms, the full prompt also failed to help without search (0.765 vs 0.755), although it may improve ranking (AUROC +0.047 [+0.013, +0.082]). Codex and Claude Code agents running the full prompt were not better than single calls on 40 claims. Test–retest noise was ±2–3 pp. All results use one inexpensive model and one biomedical
  benchmark of single-sentence claims.
]

= Introduction

LLM fact-checking pipelines usually split text into claims, retrieve evidence and verify each claim
@safe @factscore @factool @veriscore. Practitioners also write long "be rigorous" prompts that enumerate failure
modes (overgeneralization, cherry-picking, category errors), epistemic stances (Bayesian, frequentist,
empiricist) and exemplary scientists. Such prompts are hard to evaluate because they bundle many interventions.
Our contributions:

1. A system that makes each component of such a prompt independently switchable. Each component is also scored
   with a confidence in a machine-readable output contract. The execution strategy (API call vs agent, subagents,
   per-claim and per-persona calls, iteration) is configurable per pipeline step (§2).
2. A pre-registered paired evaluation on SciFact @scifact that separates the effect of the prompt from the effect
   of web search, with a measured noise floor (§3–4).

= System

*Prompt as blocks.* The original prompt (Appendix A) is split verbatim into 24 sections, for example
"Evaluate it from both bayesian and frequentist perspectives." The added sections are a NeurIPS-reviewer role,
claim classification, 0–100% scoring and confidence. The lists (45 verdict labels, degrees fully / partially /
slightly, 10 style adjectives, 63 scientists, 15 claim types) are editable. A test asserts that the all-on prompt
contains every sentence and list item of the original.

*Output contract.* Each answer ends with JSON. Per claim it holds:
- accuracy and confidence
- claim types with confidences
- every selected label with a degree, score and confidence
- 12 conditions, each with a pre-defined meaning for its score (e.g. "Bayesian perspective: posterior
  probability that the claim is true")
- a corrected claim

The JSON also holds a corrected text and a list of issues. A field is requested only while its section is
enabled. Parsing tolerates common JSON defects; a repair step re-extracts the JSON if it is still missing.

*Execution.* A run has five steps: extract (Claimify-style decomposition @claimify), check, perspective,
synthesize and repair. Each step independently chooses:
- API call (OpenAI Responses / Anthropic Messages with server-side web search) or agent (Codex CLI / Claude Code)
- model, reasoning effort, search on/off and its caps
- subagents, prompt template and prompt override

Claims can be checked as a whole text, by agent subagents, or by separate calls; scientist personas likewise.
"Iterate until accurate" re-checks the corrected text until every claim reaches a threshold. Every call passes
through one context that logs full prompts and outputs and enforces a global spend cap.

= Evaluation design (pre-registered)

The design (#link("https://github.com/BurnyCoder/auto-fact-checker/blob/main/docs/benchmark.md")[docs/benchmark.md])
was committed before any paid call.

*Data.* SciFact @scifact claims whose evidence labels are all SUPPORT or all CONTRADICT; NEI and conflicting
claims are dropped. The pool is the validation and train splits; nothing was tuned on it. The sample is balanced,
n = 200, seed 0, excluding the 6 pilot claims used only to measure cost.

*Prediction rule.* p = overall accuracy / 100; SUPPORT iff p ≥ 0.5. Unparseable outputs count as wrong.

*Systems* (all `gpt-6-luna`, effort low, one call per claim):
- A: minimal prompt, no search
- B: full default prompt, with hosted web search capped at 3 tool calls and dataset hosts blocked
- C: minimal prompt with B's search

*Metrics.* Primary: balanced accuracy, compared with an exact McNemar test @mcnemar @dietterich and a 95%
paired-bootstrap CI over 10,000 resamples @bergkirkpatrick. Secondary: accuracy with Wilson CI, macro-F1, AUROC,
Brier score.

*Hypotheses.* H1: BA(B) > BA(A). It is supported only if Δ > 0, the CI excludes 0 and p < 0.05. H2 (secondary):
C − A isolates search; B − C isolates the prompt given search.

*Sample size.* n = 200 was the largest balanced sample affordable at the pilot's worst-case cost within \$5. It
exceeds the n ≈ 155 that Connor's approximation @connor gives for δ = 10 pp at 20% discordance.

*Leakage control.* Dataset hosts were blocked. Every consulted URL was logged and flagged if it matched a dataset
host or "scifact".

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
  caption: [Per-system results; recall S / C = SUPPORT / CONTRADICT recall. #super[†] post hoc. No leak flags occurred in any system; D had one transient API failure, re-run once.])

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
  caption: [Paired comparisons on shared items. b = only the first system correct, c = only the second correct.])

*H1 is supported.* The improvement is concentrated in CONTRADICT claims (recall 0.72 → 0.88). These are expert
negations that the model accepts as plausible without evidence (Fig. 2: A gives a large cluster of CONTRADICT
claims 65–95%).

*Search explains the gain.* C − A (+0.135) is at least as large as B − A, and B − C is indistinguishable from 0.
The CI rules out a benefit of the rigorous prompt larger than about 1 pp given search. B produced 3,562 output
tokens per claim on average, vs 420 for C. Post hoc, the full prompt without search (D) also matched A (Δ +0.010 [−0.026, +0.047]). Its AUROC was higher (+0.047 [+0.013, +0.082]) with less extreme scores, a hypothesis for future pre-registered work. A Codex agent running the full prompt (E, n = 40) reached 0.876, statistically indistinguishable from the API systems on the same items. A Claude Code agent with `claude-haiku-5-5` (F) ranked claims best of all systems (AUROC 0.962) but was sceptical (SUPPORT recall 0.65). Its lower balanced accuracy versus C (p = 0.031) is one of 12 post-hoc tests and confounded by the model.

*Noise.* A re-run of A agreed on 96.5% of predictions, so differences above about 3 pp are unlikely to be sampling
noise of the generator.

#figure(image("../figures/fig2_scores_by_gold_label.png", width: 100%),
  caption: [Predicted accuracy by gold label for the 200-item systems (black bar: median).])

*Qualitative validation.* On three AI research / philosophy / engineering texts with planted errors (answer key
with sources in the repository), nine runs covered all execution presets: single call, Codex and Claude agents,
Claude subagents, per-claim agents, per-claim × per-scientist calls, and iteration. Together they agreed with the
key on all 32 claim verdicts, with complete JSON contracts. The errors are textbook, so this demonstrates function,
not accuracy. Two observations:
- Merging three scientist personas pulled scores toward 50%. For example, "the Turing test is widely accepted as
  a sufficient test for consciousness" scored 46% after synthesis vs 5–25% in single runs.
- One correction pass raised a text's self-assessed accuracy from 18% to 95%. Because the same model grades its
  own correction, this measures self-consistency, not truth.

= Related work

Decompose–retrieve–verify pipelines include FActScore @factscore, SAFE @safe, FacTool @factool,
VeriScore @veriscore and FIRE @fire; Factcheck-Bench @factcheckbench and OpenFactCheck @openfactcheck benchmark
such checkers. Claimify @claimify studies claim extraction. Our system reuses this decomposition but focuses on
making a monolithic expert prompt modular and auditable. Our ablation finding (retrieval dominates) agrees with
those pipelines' emphasis on evidence retrieval. To our knowledge, the lack of a gain from enumerating rigor
criteria has not been measured in this form before. We did not run a systematic literature search to confirm
this.

= Limitations

- *One model, one setting.* `gpt-6-luna` at low effort. Stronger models or other efforts may use the rigorous
  instructions differently.
- *One benchmark of short single claims.* SciFact scores only binary truth. The prompt's distinctive outputs
  (label scores, condition assessments with confidences, corrections) were not evaluated against human judgments,
  and the calibration of the self-reported confidences was not measured.
- *Contamination and gold semantics.* SciFact (2020) is likely in pretraining data, and its labels are relative
  to one abstract.
- *Leakage.* Host blocking and URL flagging (0 flags) cannot exclude unknown mirrors.
- *Post-hoc arms* (D, E) are exploratory. E has n = 40 and is underpowered.
- *Agent isolation.* With subscription authentication, Codex agents still load the user's global AGENTS.md; only a
  counter-instruction is applied.
- *Delegation and refusals.* In four smoke tests, Codex (`gpt-6-luna`) never actually spawned a sub-agent and
  twice reported a fabricated sub-agent answer. Claude Haiku refused some biomedical claims non-deterministically
  (bio-safety filter); one refusal is scored wrong in F.

= Conclusion

Making a long expert prompt modular allowed a clean test of what it buys. For binary verification of scientific
claims with an inexpensive model, web search is what matters. The rigorous instruction set adds cost and output
volume but no measurable accuracy. Whether its labels, condition scores and confidences are *valid* is an open,
testable question that needs human-annotated multi-dimensional judgments, which is our next step.

*Cost and reproducibility.* All experiments and development together cost \$6.64 in billed API usage
(ledger: `logs/spend.jsonl`). Commands, configurations, per-item predictions, analysis scripts and the
pre-registration are in the repository.

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
