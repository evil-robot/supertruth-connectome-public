# Protocol amendment 1 (dated 2026-09-20, written before any TEST metric was read)

PROTOCOL.md was drafted in parallel with the model code (flytrust/). Where they differ, the CODE as committed in
`6fc9540` is the pre-registered specification, because it is what the pilot runs. The differences are implementation
choices made before any label was seen; none was chosen after looking at a result.

| # | PROTOCOL.md said | Code does (binding) | Why |
|---|---|---|---|
| 1 | tanh rate units | relu with per-neuron homeostatic gain and leak | matches the fly-chess reference dynamics; keeps rates non-negative |
| 2 | gain = exp(w), w init log(syn) | gain = softplus(theta), init so gain ≈ log1p(syn) × learnable global scale | smoother near zero; log1p avoids log(0) |
| 3 | no input normalization | each neuron's incoming sum divided by its fixed initial total incoming gain ("total_gain") | 1/sqrt(in-degree) exploded (norm 4 → 1.4e6 over 8 steps) because 62.8% of edges are excitatory; documented in model.py |
| 4 | matched MLP depth 3 within 1% | depth 2 (hidden width 2,778) within 2%; measured +0.02% | width solved automatically; 2-layer is the standard matched control |
| 5 | Erdős–Rényi control keeps real presynaptic signs | ER assigns signs to match the excitatory edge fraction (0.628; measured 0.6271) | random graph has no anatomical presynaptic identity to inherit |
| 6 | sign policy zero/zero for modulatory and unclear neurotransmitters | plus/plus (nfly convention): DA, OA, 5-HT, unclear treated as excitatory, 2.28% of edges | graph built once; the digest in run.json pins it; zero/zero is an ablation, not run |
| 7 | shuffle swaps unspecified | degree-preserving Maslov–Sneppen, 10 swaps per edge | fully mixed null |
| 8 | max output tokens 2,000 (language-model arm) | 16,000 | thinking tokens count against the cap |
| 9 | AS_OF 2026-10-01 | 2026-09-20T00:00:00Z | teacher frozen on this date |
| 10 | BII heads include the four signals | BII heads = score + gate only | black-box ruling (DECISIONS.md Q9) |

Methods §3.2 and §3.5 describe the code, not the superseded protocol lines. Evidence of ordering: runs/*/run.json carry
start timestamps after this file's commit; runs/pilot.log shows the first TEST metric time.

## Amendment 1, continued (same date, same ordering evidence)

| # | PROTOCOL.md said | Code does (binding) | Why |
|---|---|---|---|
| 11 | edge-gain lr 1e-4, other params 1e-3 | one AdamW lr 1e-3, wd 0.01, cosine, clip 1.0 | single schedule for every arm; fairness across controls |
| 12 | early-stopping patience 10, max 200 epochs | patience 3, max 20 epochs | 5 min/epoch on the full graph; identical for all arms |
| 13 | ridge λ by inner CV | λ by validation-split grid | same validation split the other arms use |
| 14 | split groups by base_id / agent_id | groups = identical feature vector (teacher rows are independent draws with no base id); 70/10/20 stratified by tier/gate, seed 20260920 | teacher generator draws each row independently; qa_adversary enforces no straddle |
| 15 | Corpus A (schema-only records, 24,000 rows), Corpus B (8,000 base patients), Corpus C (60,000 windows / 3,000 agents) | ONE corpus per task: 20,000 independently drawn records (DTI) and 20,000 windows (BII), seed 20260920, spanning every tier/gate above an 8% floor | the knob-spanning generator is the primary corpus (DECISIONS Q4); the schema-only Corpus A was not built, so the out-of-distribution check is dropped from this version and named as future work |

## Amendment 1, continued (same date; language-model arm)

| # | PROTOCOL.md said | Code does (binding) | Why |
|---|---|---|---|
| 16 | language-model arm (g) = one vendor, `claude-opus-5` | language-model arm extended from one vendor to four (Anthropic, OpenAI, xAI, Google), same prompt hash, same 300 records, k=3; added at JAS's request for fairness before any model-arm result was read | requested ids are what the site's Gauntlet calls today (`gpt-5`, `grok-4`, `gemini-3-flash-preview`); each run's HOW_WE_RAN_THIS.md records the id requested, the model string the API returned (`grok-4` is served as `grok-4.3`), whether temperature 0 was accepted (Anthropic: not settable; the others: accepted), and the vendor's flagship on the retrieval date; prices from each vendor's public pricing page with URL and date (`llm_arm/prices.py`) |

## Amendment 1, continued (2026-09-21; language-model arm, POST-HOC)

| # | PROTOCOL.md said | Code does (binding) | Why |
|---|---|---|---|
| 17 | language-model arm g = paper text + instruction block, no examples, no teacher outputs | a second, post-hoc arm `g2-examples` on the same four models and served ids, the same 300 test record ids, k = 3, the same JSON schema, validator, and instruction block, PLUS a fixed block of E = 100 engine-scored examples drawn from the TRAINING split of seed 1 (`splits/dti_seed1.json:train`, record text + the same structured context + the engine's eight dimensions, composite, and tier), 20 per tier, selected with seed 20260920, identical across vendors and repeats, placed in the cached system prefix after the paper text (`llm_arm/examples.py`, `llm_arm/prompt.py`); E is the largest of {50, 100, 200} keeping the prefix under 150,000 tokens on every vendor's own tokenizer or count endpoint and under each vendor's context limit with margin (`llm_arm/examples_budget.json`: Anthropic 139,555, OpenAI 94,918, xAI 91,737, Google 109,437 tokens at E = 100; E = 200 fails the budget on every vendor); zero overlap between the example ids and the 300 scored ids and the whole TEST split, asserted before the first call and in `tests/test_llm_arm_examples.py`; runs in `llm_arm/llm_runs/<stamp>-examples/` | added AFTER the arm g results of all four vendors had been read, at the author's request ("why didn't we make it 1:1", JAS, 2026-09-21), to make the information given to the models comparable to the training labels given to the local arms (Section 3.8, Section 5). It is reported as post-hoc wherever its numbers appear, beside arm g, never in place of it; it changes no pre-registered rule and no headline. The base prompt hash (arm g) is asserted equal before any g2 call; the full prefix hash and the example-id digest are in each run's HOW_WE_RAN_THIS.md and examples.json. Gemini holds one explicit CachedContent for the run (storage priced from the pricing page, 2026-09-20); Anthropic keeps its cache_control breakpoint; OpenAI and xAI cache automatically, hit shares logged |
