# Results: connectome distillation study

Status: **partial**. Generated 2026-09-21T05:31:37+00:00 from git 92ee71f3a5f9. CI: 95% t-interval over seeds (null when fewer than 2 seeds); language-model arms: Wilson over records.
Every number below is read from a run's metrics.json or the LLM run's summary.json; a cell that says "awaiting run" has no run behind it. SYNTHETIC data, zero PHI. Trainer settings for the pilot: AdamW lr 1e-3 cosine, batch 64 (measured choice), T=8, patience 3 on VAL loss, max 20 epochs, identical across gradient arms; shuffle swaps_per_edge=10; ridge closed form (lambda by VAL loss). These differ from PROTOCOL 5 (patience 10, max 200, lr 1e-4 on edge gains) and are the pilot's settings.

## DTI arms (TEST)

| arm | composite MAE recomputed from dims (headline) | composite MAE direct head | tier accuracy | macro-F1 (support>=30) | ECE | epochs run | wall min / seed | params |
|---|---|---|---|---|---|---|---|---|
| Connectome (MaleCNS wiring, fixed) | 1.57 [1.44, 1.70] (n=2) | 1.60 [1.39, 1.82] (n=2) | 0.877 [0.846, 0.909] (n=2) | 0.876 [0.829, 0.923] (n=2) | 0.029 [0.020, 0.039] (n=2) | [16, 14] | 64.8 | 7955909 |
| Degree-preserving shuffle | 1.57 [1.04, 2.10] (n=2) | 1.61 [0.92, 2.31] (n=2) | 0.873 [0.843, 0.904] (n=2) | 0.873 [0.836, 0.909] (n=2) | 0.027 [0.013, 0.041] (n=2) | [16, 14] | 61.5 | 7955909 |
| Random graph, matched density | 1.80 [1.50, 2.09] (n=2) | 2.30 [-3.87, 8.47] (n=2) | 0.871 [0.823, 0.918] (n=2) | 0.872 [0.815, 0.929] (n=2) | 0.032 [-0.041, 0.104] (n=2) | [13, 11] | 58.1 | 7955909 |
| MLP, matched parameters | 3.56 [1.34, 5.78] (n=2) | 3.68 [1.94, 5.43] (n=2) | 0.853 [0.719, 0.986] (n=2) | 0.848 [0.649, 1.047] (n=2) | 0.049 [-0.037, 0.135] (n=2) | [8, 8] | 0.5 | 7953594 |
| Linear readout | 3.07 [3.07, 3.07] (n=2) | 3.12 [3.12, 3.12] (n=2) | 0.583 [0.583, 0.583] (n=2) | 0.428 [0.428, 0.428] (n=2) | 0.317 [0.317, 0.317] (n=2) | [1, 1] | 0.0 | 924 (closed form) |
| Claude Opus 5 given the DTI paper | 25.88 (n=300) | 25.86 (n=300) | 0.200 [0.159, 0.249] (n=300) | 0.098 | not applicable | 900 calls | 15+ min (API) | unknown |
| GPT-5 given the DTI paper | 16.07 (n=300) | 15.99 (n=300) | 0.293 [0.245, 0.347] (n=300) | 0.215 | not applicable | 900 calls | 15+ min (API) | unknown |
| Grok 4 given the DTI paper | 17.14 (n=300) | 17.11 (n=300) | 0.277 [0.229, 0.330] (n=300) | 0.202 | not applicable | 900 calls | 15+ min (API) | unknown |
| Gemini 3 Flash given the DTI paper | 9.40 (n=300) | 9.36 (n=300) | 0.447 [0.391, 0.503] (n=300) | 0.429 | not applicable | 900 calls | 15+ min (API) | unknown |
| Claude Opus 5 given the DTI paper and scored examples | 3.29 (n=300) | 3.35 (n=300) | 0.757 [0.705, 0.802] (n=300) | 0.753 | not applicable | 900 calls | 15+ min (API) | unknown |
| GPT-5 given the DTI paper and scored examples | 6.14 (n=300) | 6.17 (n=300) | 0.537 [0.480, 0.592] (n=300) | 0.528 | not applicable | 900 calls | 15+ min (API) | unknown |
| Grok 4 given the DTI paper and scored examples | 5.46 (n=300) | 5.48 (n=300) | 0.553 [0.497, 0.609] (n=300) | 0.544 | not applicable | 900 calls | 15+ min (API) | unknown |
| Gemini 3 Flash given the DTI paper and scored examples | 5.16 (n=300) | 5.15 (n=300) | 0.633 [0.577, 0.686] (n=300) | 0.619 | not applicable | 900 calls | 15+ min (API) | unknown |

```
Source: MaleCNS v1.0 (gs://flyem-male-cns/v1.0/...; sha256 in data/README.md; CC-BY 4.0; Berg et al. 2026)
 | Graph: N=166700 neurons (superclass non-null), E=6242118 edges (weight>=5), sign policy plus/plus, graph sha256 d043ac552fd6eb22833eda020224a44497a7b3cd10de4fc79388db8b7be8b952
 | Teacher: pipeline.ts commit e4785726e225e55b1dbdad201758f861f4588ebc, clock frozen at 2026-09-20T00:00:00Z
 | Data: teachers/dti_teacher.jsonl (gen_dti.ts) sha256 2aa26f37b1be93f7af42c4eebfb8f8b03a92839fc433d0e11a0df928936c4b22, run_seed 20260920, 13999/2000/4001 records, split sha256 cb23989c5192e687b635aada79e3a01ee1a645484a16d6b8eb0880cce35aa864, SYNTHETIC, zero PHI
 | Coverage: TEST only, 4001 records, 2 seeds {1,2} of protocol {1..5}; teacher dimensions excluded as degenerate: none (splits/qa_report.json)
 | Feature spec 3d57b09155d4dd58a2c75eba0fa7fe2e84882320f218fb2f4ad07f1a81e52909 | Evaluated 2026-09-21T05:31:37+00:00 | Language-model arms: claude-opus-5 (served as claude-opus-5), adaptive, effort high, max_tokens 16000, temperature not settable under adaptive thinking (not sent), k=3, N=300, prompt sha256 5e7f42957795, prices from claude-api bundled skill, Claude Code 2.1.278 retrieved 2026-09-20; gpt-5 (served as gpt-5-2025-08-07), reasoning_effort high, effort high, max_tokens 16000, temperature 0.0 requested, accepted False, k=3, N=300, prompt sha256 5e7f42957795, prices from developers.openai.com pricing and model pages retrieved 2026-09-20; grok-4 (served as grok-4.3), reasoning_effort high, effort high, max_tokens 16000, temperature 0.0 requested, accepted True, k=3, N=300, prompt sha256 5e7f42957795, prices from docs.x.ai models page and the API's language-models endpoint retrieved 2026-09-20; gemini-3-flash-preview (served as gemini-3-flash-preview), thinking_level high, effort high, max_tokens 16000, temperature 0.0 requested, accepted True, k=3, N=300, prompt sha256 5e7f42957795, prices from ai.google.dev pricing page retrieved 2026-09-20
```

### DTI per-dimension MAE (points, TEST; no dimension is degenerate, all SD >= 12.4)

| arm | provenance | consent | recency | quality | concordance | validation | breadth | stability |
|---|---|---|---|---|---|---|---|---|
| Connectome (MaleCNS wiring, fixed) | 2.40 [1.88, 2.92] (n=2) | 4.73 [2.81, 6.65] (n=2) | 6.18 [-0.91, 13.27] (n=2) | 2.81 [2.56, 3.05] (n=2) | 3.99 [1.20, 6.78] (n=2) | 3.67 [1.94, 5.40] (n=2) | 5.17 [1.10, 9.25] (n=2) | 3.11 [2.47, 3.76] (n=2) |
| Degree-preserving shuffle | 2.31 [2.18, 2.43] (n=2) | 4.20 [2.86, 5.53] (n=2) | 4.93 [2.67, 7.19] (n=2) | 2.69 [1.63, 3.74] (n=2) | 3.95 [-1.37, 9.27] (n=2) | 3.03 [2.26, 3.79] (n=2) | 4.59 [3.35, 5.84] (n=2) | 2.88 [1.44, 4.33] (n=2) |
| Random graph, matched density | 2.59 [2.22, 2.96] (n=2) | 4.65 [4.01, 5.29] (n=2) | 5.43 [4.37, 6.49] (n=2) | 2.79 [2.07, 3.51] (n=2) | 3.51 [2.90, 4.12] (n=2) | 3.31 [2.55, 4.07] (n=2) | 4.67 [-0.94, 10.28] (n=2) | 2.86 [1.47, 4.26] (n=2) |
| MLP, matched parameters | 5.24 [3.16, 7.32] (n=2) | 6.25 [4.14, 8.35] (n=2) | 7.06 [1.84, 12.28] (n=2) | 6.32 [0.29, 12.36] (n=2) | 5.61 [4.09, 7.13] (n=2) | 5.34 [2.95, 7.73] (n=2) | 6.18 [-1.09, 13.44] (n=2) | 5.81 [-0.78, 12.40] (n=2) |
| Linear readout | 4.88 [4.88, 4.88] (n=2) | 9.13 [9.13, 9.13] (n=2) | 11.66 [11.66, 11.66] (n=2) | 2.43 [2.43, 2.43] (n=2) | 3.82 [3.82, 3.82] (n=2) | 6.09 [6.09, 6.09] (n=2) | 5.09 [5.09, 5.09] (n=2) | 1.82 [1.82, 1.82] (n=2) |
| Claude Opus 5 given the DTI paper | 43.46 | 32.22 | 16.52 | 34.38 | 16.97 | 14.78 | 22.87 | 31.37 |
| GPT-5 given the DTI paper | 34.90 | 22.59 | 19.61 | 16.61 | 23.37 | 16.82 | 15.72 | 24.87 |
| Grok 4 given the DTI paper | 38.53 | 21.30 | 16.56 | 17.35 | 13.36 | 15.16 | 16.16 | 28.24 |
| Gemini 3 Flash given the DTI paper | 20.22 | 17.16 | 17.89 | 14.18 | 12.44 | 21.91 | 15.20 | 14.84 |
| Claude Opus 5 given the DTI paper and scored examples | 5.71 | 4.69 | 4.97 | 7.57 | 2.71 | 9.76 | 12.65 | 5.15 |
| GPT-5 given the DTI paper and scored examples | 7.83 | 9.51 | 12.74 | 9.61 | 6.54 | 10.18 | 13.83 | 7.19 |
| Grok 4 given the DTI paper and scored examples | 8.28 | 13.01 | 14.00 | 12.06 | 10.68 | 12.92 | 14.60 | 8.92 |
| Gemini 3 Flash given the DTI paper and scored examples | 7.99 | 8.99 | 9.78 | 8.70 | 4.97 | 9.16 | 13.96 | 6.54 |

```
Source: MaleCNS v1.0 (gs://flyem-male-cns/v1.0/...; sha256 in data/README.md; CC-BY 4.0; Berg et al. 2026)
 | Graph: N=166700 neurons (superclass non-null), E=6242118 edges (weight>=5), sign policy plus/plus, graph sha256 d043ac552fd6eb22833eda020224a44497a7b3cd10de4fc79388db8b7be8b952
 | Teacher: pipeline.ts commit e4785726e225e55b1dbdad201758f861f4588ebc, clock frozen at 2026-09-20T00:00:00Z
 | Data: teachers/dti_teacher.jsonl (gen_dti.ts) sha256 2aa26f37b1be93f7af42c4eebfb8f8b03a92839fc433d0e11a0df928936c4b22, run_seed 20260920, 13999/2000/4001 records, split sha256 cb23989c5192e687b635aada79e3a01ee1a645484a16d6b8eb0880cce35aa864, SYNTHETIC, zero PHI
 | Coverage: TEST only, 4001 records, 2 seeds {1,2} of protocol {1..5}; teacher dimensions excluded as degenerate: none (splits/qa_report.json)
 | Feature spec 3d57b09155d4dd58a2c75eba0fa7fe2e84882320f218fb2f4ad07f1a81e52909 | Evaluated 2026-09-21T05:31:37+00:00 | Language-model arms: claude-opus-5 (served as claude-opus-5), adaptive, effort high, max_tokens 16000, temperature not settable under adaptive thinking (not sent), k=3, N=300, prompt sha256 5e7f42957795, prices from claude-api bundled skill, Claude Code 2.1.278 retrieved 2026-09-20; gpt-5 (served as gpt-5-2025-08-07), reasoning_effort high, effort high, max_tokens 16000, temperature 0.0 requested, accepted False, k=3, N=300, prompt sha256 5e7f42957795, prices from developers.openai.com pricing and model pages retrieved 2026-09-20; grok-4 (served as grok-4.3), reasoning_effort high, effort high, max_tokens 16000, temperature 0.0 requested, accepted True, k=3, N=300, prompt sha256 5e7f42957795, prices from docs.x.ai models page and the API's language-models endpoint retrieved 2026-09-20; gemini-3-flash-preview (served as gemini-3-flash-preview), thinking_level high, effort high, max_tokens 16000, temperature 0.0 requested, accepted True, k=3, N=300, prompt sha256 5e7f42957795, prices from ai.google.dev pricing page retrieved 2026-09-20
```

## BII arms (TEST)

| arm | BII MAE (0-1) | gate accuracy | macro-F1 (support>=30) | ECE | epochs run | wall min / seed | params |
|---|---|---|---|---|---|---|---|
| Connectome (MaleCNS wiring, fixed) | 0.0284 [0.0244, 0.0324] (n=2) | 0.916 [0.883, 0.950] (n=2) | 0.909 [0.872, 0.946] (n=2) | 0.012 [0.010, 0.015] (n=2) | [16, 16] | 71.8 | 7811162 |
| Degree-preserving shuffle | 0.0259 [0.0240, 0.0279] (n=2) | 0.914 [0.880, 0.949] (n=2) | 0.907 [0.869, 0.944] (n=2) | 0.008 [-0.020, 0.036] (n=2) | [16, 16] | 73.1 | 7811162 |
| Random graph, matched density | 0.0258 [0.0092, 0.0424] (n=2) | 0.911 [0.863, 0.958] (n=2) | 0.903 [0.849, 0.956] (n=2) | 0.026 [-0.024, 0.076] (n=2) | [16, 16] | 74.3 | 7811162 |
| MLP, matched parameters | 0.0438 [-0.0533, 0.1408] (n=2) | 0.905 [0.818, 0.992] (n=2) | 0.898 [0.802, 0.993] (n=2) | 0.038 [0.008, 0.067] (n=2) | [11, 15] | 0.7 | 7813769 |
| Linear readout | 0.0724 [0.0724, 0.0724] (n=2) | 0.597 [0.597, 0.597] (n=2) | 0.426 [0.426, 0.426] (n=2) | 0.307 [0.307, 0.307] (n=2) | [1, 1] | 0.0 | 295 (closed form) |
| Claude Opus 5 given the DTI paper | awaiting run | | | | | | | |
| GPT-5 given the DTI paper | awaiting run | | | | | | | |
| Grok 4 given the DTI paper | awaiting run | | | | | | | |
| Gemini 3 Flash given the DTI paper | awaiting run | | | | | | | |
| Claude Opus 5 given the DTI paper and scored examples | awaiting run | | | | | | | |
| GPT-5 given the DTI paper and scored examples | awaiting run | | | | | | | |
| Grok 4 given the DTI paper and scored examples | awaiting run | | | | | | | |
| Gemini 3 Flash given the DTI paper and scored examples | awaiting run | | | | | | | |

```
Source: MaleCNS v1.0 (gs://flyem-male-cns/v1.0/...; sha256 in data/README.md; CC-BY 4.0; Berg et al. 2026)
 | Graph: N=166700 neurons (superclass non-null), E=6242118 edges (weight>=5), sign policy plus/plus, graph sha256 d043ac552fd6eb22833eda020224a44497a7b3cd10de4fc79388db8b7be8b952
 | Teacher: VIGIL commit 1cffd016b7bfa4e6ddc0dcd71a81f281fcd40031 + policy digest 5d8db364...8573859, clock frozen at 2026-09-20T00:00:00Z
 | Data: teachers/bii_teacher.jsonl (gen_bii.py) sha256 c43bb314823f19f35bd993d9860bd444663137bae48c4c836826e7cd7372f67b, run_seed 20260920, 14000/2000/4000 records, split sha256 c42920804158f4b9a3e5779cf1563f99f86818f53fe3083b0e2ca39acbf29127, SYNTHETIC, zero PHI
 | Coverage: TEST only, 4000 records, 2 seeds {1,2} of protocol {1..5}; teacher dimensions excluded as degenerate: none (splits/qa_report.json)
 | Feature spec 20a2cd2c28bcb3b5ed6728d64eaa9fce7c8ec681c57fb6018beaa855c2dea409 | Evaluated 2026-09-21T05:31:37+00:00 | Language-model arms: not run for this task
```

## Latency, cost, determinism (same records where measured)

| arm | latency per record (ms) | USD per record | determinism |
|---|---|---|---|
| Connectome (MaleCNS wiring, fixed) | 16.06 (n=1) (batch 256: 4.34 ms/record) | 0.0000 marginal API; hardware not measured | 1.000 (n=128) (two forward passes on one TEST batch per seed, bitwise equal (torch.equal)) |
| Degree-preserving shuffle | not measured (bench covers the connectome forward only) | 0.0000 marginal API; hardware not measured | 1.000 (n=128) (two forward passes on one TEST batch per seed, bitwise equal (torch.equal)) |
| Random graph, matched density | not measured (bench covers the connectome forward only) | 0.0000 marginal API; hardware not measured | 1.000 (n=128) (two forward passes on one TEST batch per seed, bitwise equal (torch.equal)) |
| MLP, matched parameters | not measured (bench covers the connectome forward only) | 0.0000 marginal API; hardware not measured | 1.000 (n=128) (two forward passes on one TEST batch per seed, bitwise equal (torch.equal)) |
| Linear readout | not measured (bench covers the connectome forward only) | 0.0000 marginal API; hardware not measured | 1.000 (n=128) (two forward passes on one TEST batch per seed, bitwise equal (torch.equal)) |
| Claude Opus 5 given the DTI paper | 13053.30 (n=900), p95 19348 | 0.1064 (20260920T154525Z/prices.json (claude-api bundled skill, Claude Code 2.1.278, retrieved 2026-09-20)) | 0.953 [0.923, 0.972] (n=300) (share of records with identical tier across k repeats) |
| GPT-5 given the DTI paper | 73221.70 (n=900), p95 102866 | 0.2647 (20260920T200058Z/prices.json (developers.openai.com pricing and model pages, retrieved 2026-09-20)) | 0.673 [0.618, 0.724] (n=300) (share of records with identical tier across k repeats) |
| Grok 4 given the DTI paper | 41579.50 (n=900), p95 64232 | 0.0420 (20260920T185412Z/prices.json (docs.x.ai models page and the API's language-models endpoint, retrieved 2026-09-20)) | 0.723 [0.670, 0.771] (n=300) (share of records with identical tier across k repeats) |
| Gemini 3 Flash given the DTI paper | 26712.80 (n=900), p95 60593 | 0.0821 (20260920T185415Z/prices.json (ai.google.dev pricing page, retrieved 2026-09-20)) | 0.840 [0.794, 0.877] (n=300) (share of records with identical tier across k repeats) |
| Claude Opus 5 given the DTI paper and scored examples | 23813.50 (n=900), p95 104128 | 0.4334 (20260920T215515Z-examples/prices.json (claude-api bundled skill, Claude Code 2.1.278, retrieved 2026-09-20)) | 0.783 [0.732, 0.826] (n=299) (share of records with identical tier across k repeats) |
| GPT-5 given the DTI paper and scored examples | 58637.80 (n=900), p95 81324 | 0.2086 (20260920T215517Z-examples/prices.json (developers.openai.com pricing and model pages, retrieved 2026-09-20)) | 0.673 [0.618, 0.724] (n=300) (share of records with identical tier across k repeats) |
| Grok 4 given the DTI paper and scored examples | 24836.00 (n=900), p95 36737 | 0.0898 (20260920T215519Z-examples/prices.json (docs.x.ai models page and the API's language-models endpoint, retrieved 2026-09-20)) | 0.667 [0.612, 0.718] (n=300) (share of records with identical tier across k repeats) |
| Gemini 3 Flash given the DTI paper and scored examples | 51821.40 (n=900), p95 58562 | 0.1182 (20260920T215521Z-examples/prices.json (ai.google.dev pricing page, retrieved 2026-09-20)) | 0.803 [0.755, 0.844] (n=300) (share of records with identical tier across k repeats) |

```
Source: MaleCNS v1.0 (gs://flyem-male-cns/v1.0/...; sha256 in data/README.md; CC-BY 4.0; Berg et al. 2026)
 | Graph: N=166700 neurons (superclass non-null), E=6242118 edges (weight>=5), sign policy plus/plus, graph sha256 d043ac552fd6eb22833eda020224a44497a7b3cd10de4fc79388db8b7be8b952
 | Teacher: pipeline.ts commit e4785726e225e55b1dbdad201758f861f4588ebc, clock frozen at 2026-09-20T00:00:00Z
 | Data: teachers/dti_teacher.jsonl (gen_dti.ts) sha256 2aa26f37b1be93f7af42c4eebfb8f8b03a92839fc433d0e11a0df928936c4b22, run_seed 20260920, 13999/2000/4001 records, split sha256 cb23989c5192e687b635aada79e3a01ee1a645484a16d6b8eb0880cce35aa864, SYNTHETIC, zero PHI
 | Coverage: TEST only, 4001 records, 2 seeds {1,2} of protocol {1..5}; teacher dimensions excluded as degenerate: none (splits/qa_report.json)
 | Feature spec 3d57b09155d4dd58a2c75eba0fa7fe2e84882320f218fb2f4ad07f1a81e52909 | Evaluated 2026-09-21T05:31:37+00:00 | Language-model arms: claude-opus-5 (served as claude-opus-5), adaptive, effort high, max_tokens 16000, temperature not settable under adaptive thinking (not sent), k=3, N=300, prompt sha256 5e7f42957795, prices from claude-api bundled skill, Claude Code 2.1.278 retrieved 2026-09-20; gpt-5 (served as gpt-5-2025-08-07), reasoning_effort high, effort high, max_tokens 16000, temperature 0.0 requested, accepted False, k=3, N=300, prompt sha256 5e7f42957795, prices from developers.openai.com pricing and model pages retrieved 2026-09-20; grok-4 (served as grok-4.3), reasoning_effort high, effort high, max_tokens 16000, temperature 0.0 requested, accepted True, k=3, N=300, prompt sha256 5e7f42957795, prices from docs.x.ai models page and the API's language-models endpoint retrieved 2026-09-20; gemini-3-flash-preview (served as gemini-3-flash-preview), thinking_level high, effort high, max_tokens 16000, temperature 0.0 requested, accepted True, k=3, N=300, prompt sha256 5e7f42957795, prices from ai.google.dev pricing page retrieved 2026-09-20
```

## Decision rules (PROTOCOL 8.1), evaluated

| task | claim | metric | threshold | value | 95% CI | seeds | verdict |
|---|---|---|---|---|---|---|---|
| dti | Fly recovers the DTI engine | composite MAE, recomputed from predicted dims (headline; TEST, mean over seeds) | <= 2.5 and CI upper <= 3.0 | 1.5715 | [1.4397, 1.7033] | 2 | **INSUFFICIENT SEEDS (2/5; point estimate meets the bar)** |
| dti | same | tier accuracy | >= 0.90, Wilson lower >= 0.88 (n = TEST records) | 0.8773 | [0.8668, 0.8871] | 2 | **INSUFFICIENT SEEDS (2/5; point estimate misses the bar)** |
| dti | same | macro-F1 (tiers with support >= 30) | >= 0.85 | 0.8762 | [0.8295, 0.9230] | 2 | **INSUFFICIENT SEEDS (2/5; point estimate meets the bar)** |
| dti | same | ECE (10 equal-mass bins) | <= 0.05 | 0.0294 | [0.0200, 0.0388] | 2 | **INSUFFICIENT SEEDS (2/5; point estimate meets the bar)** |
| dti | same | per-dimension MAE, worst of 8 (no dimension is degenerate) | <= 5.0 each | 6.1813 |  | 2 | **INSUFFICIENT SEEDS (2/5; point estimate misses the bar)** |
| bii | Fly recovers the BII scorer | BII MAE (0-1) | <= 0.0375 and CI upper <= 0.045 | 0.0284 | [0.0244, 0.0324] | 2 | **INSUFFICIENT SEEDS (2/5; point estimate meets the bar)** |
| bii | same | gate accuracy | >= 0.90 | 0.9164 | [0.8830, 0.9497] | 2 | **INSUFFICIENT SEEDS (2/5; point estimate meets the bar)** |
| bii | same | gate macro-F1 | >= 0.85 | 0.9090 |  | 2 | **INSUFFICIENT SEEDS (2/5; point estimate meets the bar)** |
| bii | same | ECE | <= 0.05 | 0.0124 |  | 2 | **INSUFFICIENT SEEDS (2/5; point estimate meets the bar)** |
| dti | Wiring matters | delta_b = MAE(shuffle) - MAE(connectome) | >= 1.0, CI lower > 0, connectome better on every seed | -0.0035 | [-0.6672, 0.6602] | 2 | **INSUFFICIENT SEEDS (2/5; point estimate misses the bar)** |
| dti | Wiring matters | delta_c = MAE(ER) - MAE(connectome) | >= 1.0, CI lower > 0, connectome better on every seed | 0.2257 | [0.0637, 0.3877] | 2 | **INSUFFICIENT SEEDS (2/5; point estimate misses the bar)** |
| dti | Fly beats the floor | MAE(ridge) - MAE(connectome) | > 0, CI lower > 0 | 1.5015 | [1.3697, 1.6333] | 2 | **INSUFFICIENT SEEDS (2/5; point estimate meets the bar)** |
| dti | Fixed graph beats matched network (framing, descriptive) | MAE(MLP) - MAE(connectome) | >= 1.0, CI lower > 0, connectome better on every seed (same margin as the wiring rule; not pre-registered) | 1.9858 | [-0.1039, 4.0754] | 2 | **INSUFFICIENT SEEDS (2/5; point estimate meets the bar)** |
| dti | same, directly predicted composite head (descriptive) | delta_b, direct head | as above | 0.0087 | [-0.4743, 0.4917] | 2 | **descriptive** |
| dti | same, directly predicted composite head (descriptive) | delta_c, direct head | as above | 0.6969 | [-5.6840, 7.0777] | 2 | **descriptive** |
| dti | same, directly predicted composite head (descriptive) | MAE(ridge) - MAE(connectome), direct head | as above | 1.5123 | [1.3000, 1.7246] | 2 | **descriptive** |
| dti | same, directly predicted composite head (descriptive) | MAE(MLP) - MAE(connectome), direct head | as above | 2.0802 | [0.5499, 3.6104] | 2 | **descriptive** |
| bii | Wiring matters | delta_b = MAE(shuffle) - MAE(connectome) | >= 0.015, CI lower > 0, connectome better on every seed | -0.0025 | [-0.0084, 0.0034] | 2 | **INSUFFICIENT SEEDS (2/5; point estimate misses the bar)** |
| bii | Wiring matters | delta_c = MAE(ER) - MAE(connectome) | >= 0.015, CI lower > 0, connectome better on every seed | -0.0027 | [-0.0233, 0.0179] | 2 | **INSUFFICIENT SEEDS (2/5; point estimate misses the bar)** |
| bii | Fly beats the floor | MAE(ridge) - MAE(connectome) | > 0, CI lower > 0 | 0.0439 | [0.0399, 0.0479] | 2 | **INSUFFICIENT SEEDS (2/5; point estimate meets the bar)** |
| bii | Fixed graph beats matched network (framing, descriptive) | MAE(MLP) - MAE(connectome) | >= 0.015, CI lower > 0, connectome better on every seed (same margin as the wiring rule; not pre-registered) | 0.0153 | [-0.0777, 0.1083] | 2 | **INSUFFICIENT SEEDS (2/5; point estimate meets the bar)** |
| dti | Faster than claude-opus-5 | p50 latency ratio claude-opus-5 / connectome (batch 1) | >= 10x to claim | 812.7443 |  | awaiting run | **PASS** |
| dti | More deterministic than claude-opus-5 | determinism share (connectome vs claude-opus-5) | connectome 1.00 and model < 0.90 | 1.000, 0.953 |  | awaiting run | **NOT CLAIMED (model 0.953, above 0.90)** |
| dti | Faster than gpt-5 | p50 latency ratio gpt-5 / connectome (batch 1) | >= 10x to claim | 4559.0402 |  | awaiting run | **PASS** |
| dti | More deterministic than gpt-5 | determinism share (connectome vs gpt-5) | connectome 1.00 and model < 0.90 | 1.000, 0.673 |  | awaiting run | **PASS** |
| dti | Faster than grok-4 | p50 latency ratio grok-4 / connectome (batch 1) | >= 10x to claim | 2588.8857 |  | awaiting run | **PASS** |
| dti | More deterministic than grok-4 | determinism share (connectome vs grok-4) | connectome 1.00 and model < 0.90 | 1.000, 0.723 |  | awaiting run | **PASS** |
| dti | Faster than gemini-3-flash-preview | p50 latency ratio gemini-3-flash-preview / connectome (batch 1) | >= 10x to claim | 1663.2327 |  | awaiting run | **PASS** |
| dti | More deterministic than gemini-3-flash-preview | determinism share (connectome vs gemini-3-flash-preview) | connectome 1.00 and model < 0.90 | 1.000, 0.840 |  | awaiting run | **PASS** |

Wiring sentence (PROTOCOL 9.4): not yet sayable (fewer than 5 seeds)

Pilot rule (PROTOCOL 8.3): seeds with both connectome and shuffle on DTI = [1, 2]; s_seed of delta_b = 0.074 points; verdict: **5 seeds stand**.

```
Source: MaleCNS v1.0 (gs://flyem-male-cns/v1.0/...; sha256 in data/README.md; CC-BY 4.0; Berg et al. 2026)
 | Graph: N=166700 neurons (superclass non-null), E=6242118 edges (weight>=5), sign policy plus/plus, graph sha256 d043ac552fd6eb22833eda020224a44497a7b3cd10de4fc79388db8b7be8b952
 | Teacher: pipeline.ts commit e4785726e225e55b1dbdad201758f861f4588ebc, clock frozen at 2026-09-20T00:00:00Z
 | Data: teachers/dti_teacher.jsonl (gen_dti.ts) sha256 2aa26f37b1be93f7af42c4eebfb8f8b03a92839fc433d0e11a0df928936c4b22, run_seed 20260920, 13999/2000/4001 records, split sha256 cb23989c5192e687b635aada79e3a01ee1a645484a16d6b8eb0880cce35aa864, SYNTHETIC, zero PHI
 | Coverage: TEST only, 4001 records, 2 seeds {1,2} of protocol {1..5}; teacher dimensions excluded as degenerate: none (splits/qa_report.json)
 | Feature spec 3d57b09155d4dd58a2c75eba0fa7fe2e84882320f218fb2f4ad07f1a81e52909 | Evaluated 2026-09-21T05:31:37+00:00 | Language-model arms: claude-opus-5 (served as claude-opus-5), adaptive, effort high, max_tokens 16000, temperature not settable under adaptive thinking (not sent), k=3, N=300, prompt sha256 5e7f42957795, prices from claude-api bundled skill, Claude Code 2.1.278 retrieved 2026-09-20; gpt-5 (served as gpt-5-2025-08-07), reasoning_effort high, effort high, max_tokens 16000, temperature 0.0 requested, accepted False, k=3, N=300, prompt sha256 5e7f42957795, prices from developers.openai.com pricing and model pages retrieved 2026-09-20; grok-4 (served as grok-4.3), reasoning_effort high, effort high, max_tokens 16000, temperature 0.0 requested, accepted True, k=3, N=300, prompt sha256 5e7f42957795, prices from docs.x.ai models page and the API's language-models endpoint retrieved 2026-09-20; gemini-3-flash-preview (served as gemini-3-flash-preview), thinking_level high, effort high, max_tokens 16000, temperature 0.0 requested, accepted True, k=3, N=300, prompt sha256 5e7f42957795, prices from ai.google.dev pricing page retrieved 2026-09-20
```

## Dataset health (splits/qa_report.json, DECISION_RULES checklist)

- **dti**: QA PASS; checks: no_id_overlap PASS, stratified PASS, no_duplicate_straddle PASS, class_floors PASS, id_not_predictive PASS, no_target_in_features PASS; rows 20000, split 13999/2000/4001; exact duplicate feature rows 0; missing 0; constant features [35, 36, 41]; exactly collinear columns 5 (one-hot groups); id AUROC 0.5092; max |corr(feature, target)| 0.97428; KS train vs test {'provenance': 0.0079, 'consent': 0.0134, 'recency': 0.0107, 'quality': 0.0133, 'concordance': 0.0174, 'validation': 0.0092, 'breadth': 0.0112, 'stability': 0.0038, 'composite': 0.006}; degenerate targets none.
- **bii**: QA PASS; checks: no_id_overlap PASS, stratified PASS, no_duplicate_straddle PASS, class_floors PASS, id_not_predictive PASS, no_target_in_features PASS; rows 20000, split 14000/2000/4000; exact duplicate feature rows 6; missing 0; constant features none; exactly collinear columns 3 (one-hot groups); id AUROC 0.503; max |corr(feature, target)| 0.73381; KS train vs test {'bii': 0.0086}; degenerate targets none.

```
Source: MaleCNS v1.0 (gs://flyem-male-cns/v1.0/...; sha256 in data/README.md; CC-BY 4.0; Berg et al. 2026)
 | Graph: N=166700 neurons (superclass non-null), E=6242118 edges (weight>=5), sign policy plus/plus, graph sha256 d043ac552fd6eb22833eda020224a44497a7b3cd10de4fc79388db8b7be8b952
 | Teacher: pipeline.ts commit e4785726e225e55b1dbdad201758f861f4588ebc, clock frozen at 2026-09-20T00:00:00Z
 | Data: teachers/dti_teacher.jsonl (gen_dti.ts) sha256 2aa26f37b1be93f7af42c4eebfb8f8b03a92839fc433d0e11a0df928936c4b22, run_seed 20260920, 13999/2000/4001 records, split sha256 cb23989c5192e687b635aada79e3a01ee1a645484a16d6b8eb0880cce35aa864, SYNTHETIC, zero PHI
 | Coverage: TEST only, 4001 records, 2 seeds {1,2} of protocol {1..5}; teacher dimensions excluded as degenerate: none (splits/qa_report.json)
 | Feature spec 3d57b09155d4dd58a2c75eba0fa7fe2e84882320f218fb2f4ad07f1a81e52909 | Evaluated 2026-09-21T05:31:37+00:00 | Language-model arms: claude-opus-5 (served as claude-opus-5), adaptive, effort high, max_tokens 16000, temperature not settable under adaptive thinking (not sent), k=3, N=300, prompt sha256 5e7f42957795, prices from claude-api bundled skill, Claude Code 2.1.278 retrieved 2026-09-20; gpt-5 (served as gpt-5-2025-08-07), reasoning_effort high, effort high, max_tokens 16000, temperature 0.0 requested, accepted False, k=3, N=300, prompt sha256 5e7f42957795, prices from developers.openai.com pricing and model pages retrieved 2026-09-20; grok-4 (served as grok-4.3), reasoning_effort high, effort high, max_tokens 16000, temperature 0.0 requested, accepted True, k=3, N=300, prompt sha256 5e7f42957795, prices from docs.x.ai models page and the API's language-models endpoint retrieved 2026-09-20; gemini-3-flash-preview (served as gemini-3-flash-preview), thinking_level high, effort high, max_tokens 16000, temperature 0.0 requested, accepted True, k=3, N=300, prompt sha256 5e7f42957795, prices from ai.google.dev pricing page retrieved 2026-09-20
```

