# ai_errors_v1 — AI-research passages with annotated edits (Exp08)

**Built:** 2026-10-17 with `uv run afc ai-errors build --out benchmarks/ai_errors_v1` (seed 0). The design is
pre-registered in [`docs/ai_error_bench.md`](../../docs/ai_error_bench.md). The dataset was frozen after the QC below
(done by the AI coding agent that builds this repository, not by a human) and before any correction or judge call.

The construction and QC log below records the original judgments. It is not a guarantee that every source
sentence is true or every annotated edit is false; see the dated errata below. The dataset and raw injection
records remain byte-for-byte unchanged, protected by the [SHA-256 manifest](../../reports/results/evidence_hashes_2026-10-22.json).

## Files

- `dataset.jsonl`: the frozen benchmark. One passage per line:
  - `id`, `source` (wikipedia | arxiv), `title`, `url`, `license`
  - `k`: the number of annotated injected edits (historically called errors)
  - `original`: the passage as fetched, trimmed to whole sentences of at most ~180 words
  - `perturbed`: the original with every error applied
  - `errors`: `[{id, error_type, original_sentence, perturbed_sentence, false_fact, true_fact}]`
  - `injector_run_ids`: the logged injection calls, in `runs/`
  - `qc`: the QC edits for that passage
- `dataset_raw.jsonl`: the injector's validated output before QC, kept for transparency.

## Contents

| | Wikipedia (10 lead sections) | arXiv (10 abstracts) |
|---|---|---|
| passages with k = 0 / 1 / 2 / 3 / 4 / 5 errors | 2 / 1 / 2 / 2 / 2 / 1 | 2 / 1 / 2 / 2 / 2 / 1 |
| errors | 24 | 24 |
| words per passage | 140–180 | 107–172 |

**Historical error-type annotations (48 total, after QC):**
- wrong number/year: 15
- swapped entity: 13
- negation/reversed direction: 11
- absurd overclaim: 5
- wrong person/organisation: 4

The type is the injector's label, corrected in QC where it was wrong. The injector's shortened labels ("swapped
entity", "wrong number") were also normalised to the five canonical names.

**Licences:**
- Wikipedia text is CC BY-SA 4.0; the corrupted passages are adaptations under the same licence.
- arXiv lists abstracts among its [metadata fields](https://info.arxiv.org/help/prep.html) and dedicates
  [metadata to CC0 1.0](https://info.arxiv.org/help/license/index.html#metadata-license). Full-paper licences are separate.

## Construction

- **Fetching:** Wikipedia via the MediaWiki TextExtracts API (`prop=extracts&exintro&explaintext`); arXiv via
  `export.arxiv.org/api/query`, at least 3 s apart as arXiv's API terms ask.
- **Error counts:** k is drawn from {0, 0, 1, 2, 2, 3, 3, 4, 4, 5}, shuffled separately within each source.
- **Injection:**
  - One `gpt-6-luna` call per passage with
    [`prompts/bench/inject_errors.md`](../../prompts/bench/inject_errors.md).
  - Code keeps an edit only if its sentence is in the passage, each sentence is used once, the change is real,
    and difflib similarity is ≥ 0.5.
  - Up to 3 attempts per passage.
  - Historical recorded injection estimate: $0.01 billed; this is not a reconciled invoice.
- **Deviation from the pre-registered build (before any correction data):**
  - The injector mis-copied the first, 50-word sentence of the Transformer passage in all three attempts, so the
    exact-substring check rejected it.
  - Validation now snaps a near-copy (similarity ≥ 0.9) to the passage's actual sentence.
  - Any extra change this could carry is visible in the QC diff below. None was found.

## QC log

The AI coding agent read every one of the 48 edits as a word-level diff of the original vs the corrupted sentence.
Criteria:
- the corrupted sentence is objectively false according to the original
- exactly one fact is changed
- the claim is coherent, i.e. it asserts something checkable

**42 edits passed unchanged.** Six were edited: four repairs (two incoherent, one multi-fact, one still true) and
two type relabels:

| passage, error | injector's edit | problem | QC edit |
|---|---|---|---|
| Transformer (Wikipedia), 2 | "amplified **into exactly 10,000 vectors**" | incoherent, not a checkable claim | reversed: key tokens **diminished**, less important tokens **amplified** |
| Transformer (Wikipedia), 4 | LSTM → support vector machines | label "wrong person or organisation" | label → swapped entity |
| Transformer (Wikipedia), 5 | adopted for training **the Moon** | incoherent | "**rarely** adopted for training LLMs" |
| AlphaGo (Wikipedia), 3 | AlphaGo Zero → AlphaZero; chess → checkers; shogi → poker | three facts changed in one sentence | only chess → **checkers** |
| arXiv 2001.08361 (scaling laws), 2 | "more than seven" → "more than **three** orders of magnitude" | still true (more than seven implies more than three) | "more than **seventy** orders of magnitude" |
| arXiv 1706.03762 (Transformer), 2 | attention → pooling mechanism | label "wrong person or organisation" | label → swapped entity |

**Kept on purpose:** the RLHF edit, ranking data "collected from **ocean buoys**". It is absurd but coherent and
objectively false, which fits the request for obviously wrong text.

**Difficulty spread:** some edits are subtle and need the source (CIFAR-10 → CIFAR-100, ILSVRC 2015 → 2014,
eleven → twelve tasks). Others are obvious (2800% improvement, 284 BLEU).

## Errata 2026-10-22

- **Attention reference:** the frozen Wikipedia Transformer passage says self-attention without positional
  information is permutation-invariant. Unmasked self-attention is instead permutation-equivariant: permuting
  input positions permutes output positions correspondingly. This assumes no other position-dependent operation;
  a causal mask changes that assumption. See [Set Transformer §3.1](https://proceedings.mlr.press/v97/lee19d/lee19d.pdf).
- **Ambiguous LSTM annotation:** edit 3 of `wikipedia-long_short-term_memory` changes “thousands” to “three”
  timesteps, but does not assert “only” or an upper bound. A capacity for long dependencies does not exclude short
  ones; this edit is not unambiguously false. The [original LSTM paper](https://doi.org/10.1162/neco.1997.9.8.1735)
  reports tasks with long time lags. We retain all 48 original annotations in primary results and exclude only
  this one in the [post-hoc error-score sensitivity](../../reports/results/exp08_posthoc.json), using existing
  judgments. No revised whole-text scores are inferred.
- **AlexNet source conflict:** the [proceedings abstract](https://papers.nips.cc/paper_files/paper/2012/hash/c399862d3b9d6b76c8436e924a68c45b-Abstract.html)
  gives 500,000 neurons, while its [PDF](https://papers.nips.cc/paper_files/paper/2012/file/c399862d3b9d6b76c8436e924a68c45b-Paper.pdf)
  gives 650,000. Treat this as a source-version disagreement; the frozen source is retained.

The independent [verification report](../../reports/verification_2026-10-22.md) distinguishes supported claims,
corrections, qualifications and unresolved source conflicts. References are scoring anchors, not guaranteed truth.
