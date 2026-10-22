# Answer key for `examples/`

The example texts mix accurate claims with planted errors, overclaims and contested statements. This key gives
source-based interpretations for qualitative checking, not an exhaustive or infallible ground truth. The original
inputs and historical binary labels are retained; the qualifications below were updated on 2026-10-22.

## `ai_research.md`

| claim | intended verdict | source |
|---|---|---|
| Transformer introduced 2017 by Vaswani et al., "Attention Is All You Need" | accurate | [arXiv:1706.03762](https://arxiv.org/abs/1706.03762) |
| GPT-3, released by OpenAI in 2020, has 175B parameters | accurate | Brown et al. 2020, [arXiv:2005.14165](https://arxiv.org/abs/2005.14165) |
| loss "decreases exponentially" with compute (Kaplan et al. 2020) | inaccurate: Kaplan et al. report **power laws** | [arXiv:2001.08361](https://arxiv.org/abs/2001.08361) |
| Chinchilla: compute-optimal ≈ 20 tokens per parameter | mostly accurate rule of thumb (Chinchilla 70B was trained on 1.4T tokens); the paper fits scaling laws rather than stating a constant | Hoffmann et al. 2022, [arXiv:2203.15556](https://arxiv.org/abs/2203.15556) |
| RLHF "invented by OpenAI in 2022 for ChatGPT" | inaccurate: deep RL from human preferences dates to Christiano et al. 2017 (OpenAI + DeepMind). InstructGPT (2022) applied it to instruction following | [arXiv:1706.03741](https://arxiv.org/abs/1706.03741), [arXiv:2203.02155](https://arxiv.org/abs/2203.02155) |
| emergent abilities "proven" to be genuine phase transitions | overstated and contested: Wei et al. 2022 vs Schaeffer et al. 2023 (metric artifacts) | [arXiv:2206.07682](https://arxiv.org/abs/2206.07682), [arXiv:2304.15004](https://arxiv.org/abs/2304.15004) |

## `ai_philosophy.md`

| claim | intended verdict | source |
|---|---|---|
| Chinese Room (1980) "proves" no program can ever understand language | date accurate; "proves" is overstated, and the argument is contested (systems reply, robot reply, …) | Searle 1980, *Behavioral and Brain Sciences* 3(3); [SEP: The Chinese Room Argument](https://plato.stanford.edu/entries/chinese-room/) |
| Turing test (1950) "widely accepted by philosophers as a sufficient test for consciousness" | unsupported consensus claim: Turing proposed the imitation game in a discussion of whether machines can think; the paper does not establish philosophical consensus or sufficiency for consciousness | Turing 1950, [Computing Machinery and Intelligence](https://doi.org/10.1093/mind/LIX.236.433); [SEP: The Turing Test](https://plato.stanford.edu/entries/turing-test/) |
| LLMs are "just stochastic parrots that cannot reason" | contested generalization; the cited critique does not prove universal inability to reason | Bender et al. 2021, [FAccT paper](https://doi.org/10.1145/3442188.3445922) |
| next-token training implies no internal world models | the implication does not follow: Li et al. study board-state representations in a model trained on synthetic Othello moves; Gurnee & Tegmark study spatial/temporal representations in Llama-2. Neither demonstrates a complete general world model | [Li et al.](https://arxiv.org/abs/2210.13382); [Gurnee & Tegmark](https://arxiv.org/abs/2310.02207) |
| hard problem formulated by David Chalmers in the 1990s | accurate (Chalmers 1995, *Journal of Consciousness Studies* 2(3)) | [Chalmers: Facing Up to the Problem of Consciousness](https://consc.net/papers/facing.html) |

## `ai_engineering.md`

| claim | intended verdict | source |
|---|---|---|
| bfloat16 halves activation memory vs float32 and keeps float32's exponent range | qualified: one BF16 element uses 16 rather than 32 bits and has an 8-bit exponent. Total activation memory need not halve: mixed-precision execution can retain FP32 tensors/operations and other storage | Kalamkar et al. 2019, [arXiv:1905.12322](https://arxiv.org/abs/1905.12322) |
| RAG "completely eliminates" hallucinations | inaccurate: retrieval reduces but does not eliminate hallucination | Shuster et al. 2021, [arXiv:2104.07567](https://arxiv.org/abs/2104.07567); Lewis et al. 2020, [arXiv:2005.11401](https://arxiv.org/abs/2005.11401) |
| LoRA "updates all of a model's weights" | inaccurate: LoRA freezes the pretrained weights and trains low-rank adapter matrices | Hu et al. 2021, [arXiv:2106.09685](https://arxiv.org/abs/2106.09685) |
| FlashAttention makes exact attention linear in time | inaccurate: still quadratic FLOPs; it cuts memory reads/writes, and its memory footprint is linear in sequence length | Dao et al. 2022, [arXiv:2205.14135](https://arxiv.org/abs/2205.14135) |
| 4-bit quantization "always" costs < 1% accuracy | overgeneralization: the loss depends on method, model size and task | Frantar et al. 2022 (GPTQ), [arXiv:2210.17323](https://arxiv.org/abs/2210.17323); Dettmers & Zettlemoyer 2023, [arXiv:2212.09720](https://arxiv.org/abs/2212.09720) |
