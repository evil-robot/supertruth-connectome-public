# Results: connectome distillation study

Status: **complete**. Generated 2026-09-22T12:44:41+00:00 from git d8c9ae8e7ea5. CI: 95% t-interval over seeds (null when fewer than 2 seeds); language-model arms: Wilson over records.
Every number below is read from a run's metrics.json or the LLM run's summary.json; a cell that says "awaiting run" has no run behind it. SYNTHETIC data, zero PHI. Trainer settings for the pilot: AdamW lr 1e-3 cosine, batch 64 (measured choice), T=8, patience 3 on VAL loss, max 20 epochs, identical across gradient arms; shuffle swaps_per_edge=10; ridge closed form (lambda by VAL loss). These differ from PROTOCOL 5 (patience 10, max 200, lr 1e-4 on edge gains) and are the pilot's settings.

## DTI arms (TEST)

| arm | composite MAE recomputed from dims (headline) | composite MAE direct head | tier accuracy | macro-F1 (support>=30) | ECE | epochs run | wall min / seed | params |
|---|---|---|---|---|---|---|---|---|
| Connectome (MaleCNS wiring, fixed) | 1.74 [1.41, 2.07] (n=5) | 1.78 [1.54, 2.01] (n=5) | 0.872 [0.864, 0.880] (n=5) | 0.872 [0.864, 0.879] (n=5) | 0.023 [0.011, 0.035] (n=5) | [16, 14, 15, 10, 12] | 56.3 | 7955909 |
| Degree-preserving shuffle | 1.60 [1.52, 1.68] (n=5) | 1.77 [1.45, 2.09] (n=5) | 0.872 [0.869, 0.876] (n=5) | 0.873 [0.869, 0.876] (n=5) | 0.028 [0.023, 0.032] (n=5) | [16, 14, 15, 14, 18] | 65.5 | 7955909 |
| Random graph, matched density | 1.78 [1.73, 1.83] (n=5) | 2.13 [1.64, 2.62] (n=5) | 0.869 [0.864, 0.874] (n=5) | 0.869 [0.864, 0.875] (n=5) | 0.027 [0.019, 0.036] (n=5) | [13, 11, 11, 10, 10] | 53.1 | 7955909 |
| MLP, matched parameters | 3.71 [2.85, 4.57] (n=5) | 4.06 [3.17, 4.95] (n=5) | 0.854 [0.842, 0.866] (n=5) | 0.851 [0.834, 0.868] (n=5) | 0.044 [0.029, 0.058] (n=5) | [8, 8, 6, 8, 10] | 0.5 | 7953594 |
| Linear readout | 3.07 [3.07, 3.07] (n=5) | 3.12 [3.12, 3.12] (n=5) | 0.583 [0.583, 0.583] (n=5) | 0.428 [0.428, 0.428] (n=5) | 0.317 [0.317, 0.317] (n=5) | [1, 1, 1, 1, 1] | 0.0 | 924 (closed form) |
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
 | Coverage: TEST only, 4001 records, 5 seeds {1,2,3,4,5} of protocol {1..5}; teacher dimensions excluded as degenerate: none (splits/qa_report.json)
 | Feature spec 3d57b09155d4dd58a2c75eba0fa7fe2e84882320f218fb2f4ad07f1a81e52909 | Evaluated 2026-09-22T12:44:41+00:00 | Language-model arms: claude-opus-5 (served as claude-opus-5), adaptive, effort high, max_tokens 16000, temperature not settable under adaptive thinking (not sent), k=3, N=300, prompt sha256 5e7f42957795, prices from claude-api bundled skill, Claude Code 2.1.278 retrieved 2026-09-20; gpt-5 (served as gpt-5-2025-08-07), reasoning_effort high, effort high, max_tokens 16000, temperature 0.0 requested, accepted False, k=3, N=300, prompt sha256 5e7f42957795, prices from developers.openai.com pricing and model pages retrieved 2026-09-20; grok-4 (served as grok-4.3), reasoning_effort high, effort high, max_tokens 16000, temperature 0.0 requested, accepted True, k=3, N=300, prompt sha256 5e7f42957795, prices from docs.x.ai models page and the API's language-models endpoint retrieved 2026-09-20; gemini-3-flash-preview (served as gemini-3-flash-preview), thinking_level high, effort high, max_tokens 16000, temperature 0.0 requested, accepted True, k=3, N=300, prompt sha256 5e7f42957795, prices from ai.google.dev pricing page retrieved 2026-09-20
```

### DTI per-dimension MAE (points, TEST; no dimension is degenerate, all SD >= 12.4)

| arm | provenance | consent | recency | quality | concordance | validation | breadth | stability |
|---|---|---|---|---|---|---|---|---|
| Connectome (MaleCNS wiring, fixed) | 2.51 [2.35, 2.67] (n=5) | 4.89 [4.62, 5.15] (n=5) | 6.35 [5.45, 7.24] (n=5) | 3.18 [2.30, 4.06] (n=5) | 4.50 [3.33, 5.68] (n=5) | 3.91 [3.47, 4.35] (n=5) | 5.17 [4.83, 5.51] (n=5) | 3.09 [2.99, 3.19] (n=5) |
| Degree-preserving shuffle | 2.30 [2.22, 2.37] (n=5) | 4.39 [4.12, 4.67] (n=5) | 5.08 [4.71, 5.46] (n=5) | 2.74 [2.59, 2.88] (n=5) | 3.68 [3.20, 4.16] (n=5) | 2.95 [2.69, 3.21] (n=5) | 4.55 [4.43, 4.67] (n=5) | 2.74 [2.53, 2.94] (n=5) |
| Random graph, matched density | 2.56 [2.44, 2.68] (n=5) | 4.79 [4.51, 5.08] (n=5) | 5.59 [5.33, 5.85] (n=5) | 2.75 [2.64, 2.85] (n=5) | 3.73 [3.44, 4.02] (n=5) | 3.36 [2.98, 3.74] (n=5) | 4.58 [4.15, 5.00] (n=5) | 2.92 [2.63, 3.21] (n=5) |
| MLP, matched parameters | 5.63 [4.23, 7.02] (n=5) | 6.43 [5.42, 7.45] (n=5) | 7.28 [6.24, 8.33] (n=5) | 5.88 [5.00, 6.75] (n=5) | 6.65 [3.75, 9.55] (n=5) | 6.64 [4.09, 9.19] (n=5) | 6.37 [5.22, 7.52] (n=5) | 5.22 [4.17, 6.27] (n=5) |
| Linear readout | 4.88 [4.88, 4.88] (n=5) | 9.13 [9.13, 9.13] (n=5) | 11.66 [11.66, 11.66] (n=5) | 2.43 [2.43, 2.43] (n=5) | 3.82 [3.82, 3.82] (n=5) | 6.09 [6.09, 6.09] (n=5) | 5.09 [5.09, 5.09] (n=5) | 1.82 [1.82, 1.82] (n=5) |
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
 | Coverage: TEST only, 4001 records, 5 seeds {1,2,3,4,5} of protocol {1..5}; teacher dimensions excluded as degenerate: none (splits/qa_report.json)
 | Feature spec 3d57b09155d4dd58a2c75eba0fa7fe2e84882320f218fb2f4ad07f1a81e52909 | Evaluated 2026-09-22T12:44:41+00:00 | Language-model arms: claude-opus-5 (served as claude-opus-5), adaptive, effort high, max_tokens 16000, temperature not settable under adaptive thinking (not sent), k=3, N=300, prompt sha256 5e7f42957795, prices from claude-api bundled skill, Claude Code 2.1.278 retrieved 2026-09-20; gpt-5 (served as gpt-5-2025-08-07), reasoning_effort high, effort high, max_tokens 16000, temperature 0.0 requested, accepted False, k=3, N=300, prompt sha256 5e7f42957795, prices from developers.openai.com pricing and model pages retrieved 2026-09-20; grok-4 (served as grok-4.3), reasoning_effort high, effort high, max_tokens 16000, temperature 0.0 requested, accepted True, k=3, N=300, prompt sha256 5e7f42957795, prices from docs.x.ai models page and the API's language-models endpoint retrieved 2026-09-20; gemini-3-flash-preview (served as gemini-3-flash-preview), thinking_level high, effort high, max_tokens 16000, temperature 0.0 requested, accepted True, k=3, N=300, prompt sha256 5e7f42957795, prices from ai.google.dev pricing page retrieved 2026-09-20
```

## BII arms (TEST)

| arm | BII MAE (0-1) | gate accuracy | macro-F1 (support>=30) | ECE | epochs run | wall min / seed | params |
|---|---|---|---|---|---|---|---|
| Connectome (MaleCNS wiring, fixed) | 0.0272 [0.0247, 0.0297] (n=5) | 0.916 [0.912, 0.919] (n=5) | 0.908 [0.904, 0.913] (n=5) | 0.012 [0.010, 0.014] (n=5) | [16, 16, 14, 17, 15] | 67.5 | 7811162 |
| Degree-preserving shuffle | 0.0278 [0.0243, 0.0312] (n=5) | 0.913 [0.908, 0.917] (n=5) | 0.905 [0.900, 0.910] (n=5) | 0.012 [0.006, 0.017] (n=5) | [16, 16, 14, 20, 16] | 74.0 | 7811162 |
| Random graph, matched density | 0.0288 [0.0233, 0.0343] (n=5) | 0.909 [0.903, 0.914] (n=5) | 0.900 [0.893, 0.907] (n=5) | 0.019 [0.011, 0.028] (n=5) | [16, 16, 13, 11, 13] | 65.3 | 7811162 |
| MLP, matched parameters | 0.0504 [0.0362, 0.0646] (n=5) | 0.910 [0.900, 0.919] (n=5) | 0.902 [0.892, 0.912] (n=5) | 0.032 [0.025, 0.039] (n=5) | [11, 15, 10, 13, 13] | 0.7 | 7813769 |
| Linear readout | 0.0724 [0.0724, 0.0724] (n=5) | 0.597 [0.597, 0.597] (n=5) | 0.426 [0.426, 0.426] (n=5) | 0.307 [0.307, 0.307] (n=5) | [1, 1, 1, 1, 1] | 0.0 | 295 (closed form) |
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
 | Coverage: TEST only, 4000 records, 5 seeds {1,2,3,4,5} of protocol {1..5}; teacher dimensions excluded as degenerate: none (splits/qa_report.json)
 | Feature spec 20a2cd2c28bcb3b5ed6728d64eaa9fce7c8ec681c57fb6018beaa855c2dea409 | Evaluated 2026-09-22T12:44:41+00:00 | Language-model arms: not run for this task
```

## Latency, cost, determinism (same records where measured)

| arm | latency per record (ms) | USD per record | determinism |
|---|---|---|---|
| Connectome (MaleCNS wiring, fixed) | 16.06 (n=1) (batch 256: 4.34 ms/record) | 0.0000 marginal API; hardware not measured | 1.000 (n=320) (two forward passes on one TEST batch per seed, bitwise equal (torch.equal)) |
| Degree-preserving shuffle | not measured (bench covers the connectome forward only) | 0.0000 marginal API; hardware not measured | 1.000 (n=320) (two forward passes on one TEST batch per seed, bitwise equal (torch.equal)) |
| Random graph, matched density | not measured (bench covers the connectome forward only) | 0.0000 marginal API; hardware not measured | 1.000 (n=320) (two forward passes on one TEST batch per seed, bitwise equal (torch.equal)) |
| MLP, matched parameters | not measured (bench covers the connectome forward only) | 0.0000 marginal API; hardware not measured | 1.000 (n=320) (two forward passes on one TEST batch per seed, bitwise equal (torch.equal)) |
| Linear readout | not measured (bench covers the connectome forward only) | 0.0000 marginal API; hardware not measured | 1.000 (n=320) (two forward passes on one TEST batch per seed, bitwise equal (torch.equal)) |
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
 | Coverage: TEST only, 4001 records, 5 seeds {1,2,3,4,5} of protocol {1..5}; teacher dimensions excluded as degenerate: none (splits/qa_report.json)
 | Feature spec 3d57b09155d4dd58a2c75eba0fa7fe2e84882320f218fb2f4ad07f1a81e52909 | Evaluated 2026-09-22T12:44:41+00:00 | Language-model arms: claude-opus-5 (served as claude-opus-5), adaptive, effort high, max_tokens 16000, temperature not settable under adaptive thinking (not sent), k=3, N=300, prompt sha256 5e7f42957795, prices from claude-api bundled skill, Claude Code 2.1.278 retrieved 2026-09-20; gpt-5 (served as gpt-5-2025-08-07), reasoning_effort high, effort high, max_tokens 16000, temperature 0.0 requested, accepted False, k=3, N=300, prompt sha256 5e7f42957795, prices from developers.openai.com pricing and model pages retrieved 2026-09-20; grok-4 (served as grok-4.3), reasoning_effort high, effort high, max_tokens 16000, temperature 0.0 requested, accepted True, k=3, N=300, prompt sha256 5e7f42957795, prices from docs.x.ai models page and the API's language-models endpoint retrieved 2026-09-20; gemini-3-flash-preview (served as gemini-3-flash-preview), thinking_level high, effort high, max_tokens 16000, temperature 0.0 requested, accepted True, k=3, N=300, prompt sha256 5e7f42957795, prices from ai.google.dev pricing page retrieved 2026-09-20
```

## Decision rules (PROTOCOL 8.1), evaluated

| task | claim | metric | threshold | value | 95% CI | seeds | verdict |
|---|---|---|---|---|---|---|---|
| dti | Fly recovers the DTI engine | composite MAE, recomputed from predicted dims (headline; TEST, mean over seeds) | <= 2.5 and CI upper <= 3.0 | 1.7400 | [1.4085, 2.0714] | 5 | **PASS** |
| dti | same | tier accuracy | >= 0.90, Wilson lower >= 0.88 (n = TEST records) | 0.8720 | [0.8613, 0.8820] | 5 | **FAIL** |
| dti | same | macro-F1 (tiers with support >= 30) | >= 0.85 | 0.8716 | [0.8640, 0.8792] | 5 | **PASS** |
| dti | same | ECE (10 equal-mass bins) | <= 0.05 | 0.0232 | [0.0114, 0.0351] | 5 | **PASS** |
| dti | same | per-dimension MAE, worst of 8 (no dimension is degenerate) | <= 5.0 each | 6.3473 |  | 5 | **FAIL** |
| bii | Fly recovers the BII scorer | BII MAE (0-1) | <= 0.0375 and CI upper <= 0.045 | 0.0272 | [0.0247, 0.0297] | 5 | **PASS** |
| bii | same | gate accuracy | >= 0.90 | 0.9158 | [0.9122, 0.9194] | 5 | **PASS** |
| bii | same | gate macro-F1 | >= 0.85 | 0.9084 |  | 5 | **PASS** |
| bii | same | ECE | <= 0.05 | 0.0119 |  | 5 | **PASS** |
| dti | Wiring matters | delta_b = MAE(shuffle) - MAE(connectome) | >= 1.0, CI lower > 0, connectome better on every seed | -0.1402 | [-0.4472, 0.1668] | 5 | **FAIL** |
| dti | Wiring matters | delta_c = MAE(ER) - MAE(connectome) | >= 1.0, CI lower > 0, connectome better on every seed | 0.0393 | [-0.3060, 0.3847] | 5 | **FAIL** |
| dti | Fly beats the floor | MAE(ridge) - MAE(connectome) | > 0, CI lower > 0 | 1.3330 | [1.0016, 1.6645] | 5 | **PASS** |
| dti | Fixed graph beats matched network (framing, descriptive) | MAE(MLP) - MAE(connectome) | >= 1.0, CI lower > 0, connectome better on every seed (same margin as the wiring rule; not pre-registered) | 1.9680 | [1.2837, 2.6523] | 5 | **PASS** |
| dti | same, directly predicted composite head (descriptive) | delta_b, direct head | as above | -0.0033 | [-0.3914, 0.3849] | 5 | **descriptive** |
| dti | same, directly predicted composite head (descriptive) | delta_c, direct head | as above | 0.3548 | [-0.2328, 0.9424] | 5 | **descriptive** |
| dti | same, directly predicted composite head (descriptive) | MAE(ridge) - MAE(connectome), direct head | as above | 1.3394 | [1.1030, 1.5758] | 5 | **descriptive** |
| dti | same, directly predicted composite head (descriptive) | MAE(MLP) - MAE(connectome), direct head | as above | 2.2828 | [1.5253, 3.0402] | 5 | **descriptive** |
| bii | Wiring matters | delta_b = MAE(shuffle) - MAE(connectome) | >= 0.015, CI lower > 0, connectome better on every seed | 0.0005 | [-0.0039, 0.0050] | 5 | **FAIL** |
| bii | Wiring matters | delta_c = MAE(ER) - MAE(connectome) | >= 0.015, CI lower > 0, connectome better on every seed | 0.0016 | [-0.0064, 0.0095] | 5 | **FAIL** |
| bii | Fly beats the floor | MAE(ridge) - MAE(connectome) | > 0, CI lower > 0 | 0.0452 | [0.0427, 0.0476] | 5 | **PASS** |
| bii | Fixed graph beats matched network (framing, descriptive) | MAE(MLP) - MAE(connectome) | >= 0.015, CI lower > 0, connectome better on every seed (same margin as the wiring rule; not pre-registered) | 0.0232 | [0.0077, 0.0387] | 5 | **PASS** |
| dti | Faster than claude-opus-5 | p50 latency ratio claude-opus-5 / connectome (batch 1) | >= 10x to claim | 812.7443 |  | awaiting run | **PASS** |
| dti | More deterministic than claude-opus-5 | determinism share (connectome vs claude-opus-5) | connectome 1.00 and model < 0.90 | 1.000, 0.953 |  | awaiting run | **NOT CLAIMED (model 0.953, above 0.90)** |
| dti | Faster than gpt-5 | p50 latency ratio gpt-5 / connectome (batch 1) | >= 10x to claim | 4559.0402 |  | awaiting run | **PASS** |
| dti | More deterministic than gpt-5 | determinism share (connectome vs gpt-5) | connectome 1.00 and model < 0.90 | 1.000, 0.673 |  | awaiting run | **PASS** |
| dti | Faster than grok-4 | p50 latency ratio grok-4 / connectome (batch 1) | >= 10x to claim | 2588.8857 |  | awaiting run | **PASS** |
| dti | More deterministic than grok-4 | determinism share (connectome vs grok-4) | connectome 1.00 and model < 0.90 | 1.000, 0.723 |  | awaiting run | **PASS** |
| dti | Faster than gemini-3-flash-preview | p50 latency ratio gemini-3-flash-preview / connectome (batch 1) | >= 10x to claim | 1663.2327 |  | awaiting run | **PASS** |
| dti | More deterministic than gemini-3-flash-preview | determinism share (connectome vs gemini-3-flash-preview) | connectome 1.00 and model < 0.90 | 1.000, 0.840 |  | awaiting run | **PASS** |

Wiring sentence (PROTOCOL 9.4): wiring did not matter

Pilot rule (PROTOCOL 8.3): seeds with both connectome and shuffle on DTI = [1, 2, 3, 4, 5]; s_seed of delta_b = 0.247 points; verdict: **5 seeds stand**.

```
Source: MaleCNS v1.0 (gs://flyem-male-cns/v1.0/...; sha256 in data/README.md; CC-BY 4.0; Berg et al. 2026)
 | Graph: N=166700 neurons (superclass non-null), E=6242118 edges (weight>=5), sign policy plus/plus, graph sha256 d043ac552fd6eb22833eda020224a44497a7b3cd10de4fc79388db8b7be8b952
 | Teacher: pipeline.ts commit e4785726e225e55b1dbdad201758f861f4588ebc, clock frozen at 2026-09-20T00:00:00Z
 | Data: teachers/dti_teacher.jsonl (gen_dti.ts) sha256 2aa26f37b1be93f7af42c4eebfb8f8b03a92839fc433d0e11a0df928936c4b22, run_seed 20260920, 13999/2000/4001 records, split sha256 cb23989c5192e687b635aada79e3a01ee1a645484a16d6b8eb0880cce35aa864, SYNTHETIC, zero PHI
 | Coverage: TEST only, 4001 records, 5 seeds {1,2,3,4,5} of protocol {1..5}; teacher dimensions excluded as degenerate: none (splits/qa_report.json)
 | Feature spec 3d57b09155d4dd58a2c75eba0fa7fe2e84882320f218fb2f4ad07f1a81e52909 | Evaluated 2026-09-22T12:44:41+00:00 | Language-model arms: claude-opus-5 (served as claude-opus-5), adaptive, effort high, max_tokens 16000, temperature not settable under adaptive thinking (not sent), k=3, N=300, prompt sha256 5e7f42957795, prices from claude-api bundled skill, Claude Code 2.1.278 retrieved 2026-09-20; gpt-5 (served as gpt-5-2025-08-07), reasoning_effort high, effort high, max_tokens 16000, temperature 0.0 requested, accepted False, k=3, N=300, prompt sha256 5e7f42957795, prices from developers.openai.com pricing and model pages retrieved 2026-09-20; grok-4 (served as grok-4.3), reasoning_effort high, effort high, max_tokens 16000, temperature 0.0 requested, accepted True, k=3, N=300, prompt sha256 5e7f42957795, prices from docs.x.ai models page and the API's language-models endpoint retrieved 2026-09-20; gemini-3-flash-preview (served as gemini-3-flash-preview), thinking_level high, effort high, max_tokens 16000, temperature 0.0 requested, accepted True, k=3, N=300, prompt sha256 5e7f42957795, prices from ai.google.dev pricing page retrieved 2026-09-20
```

## Dataset health (splits/qa_report.json, DECISION_RULES checklist)

- **dti**: QA PASS; checks: no_id_overlap PASS, stratified PASS, no_duplicate_straddle PASS, class_floors PASS, id_not_predictive PASS, no_target_in_features PASS; rows 20000, split 13999/2000/4001; exact duplicate feature rows 0; missing 0; constant features [35, 36, 41]; exactly collinear columns 5 (one-hot groups); id AUROC 0.5092; max |corr(feature, target)| 0.97428; KS train vs test {'provenance': 0.0079, 'consent': 0.0134, 'recency': 0.0107, 'quality': 0.0133, 'concordance': 0.0174, 'validation': 0.0092, 'breadth': 0.0112, 'stability': 0.0038, 'composite': 0.006}; degenerate targets none.
- **bii**: QA PASS; checks: no_id_overlap PASS, stratified PASS, no_duplicate_straddle PASS, class_floors PASS, id_not_predictive PASS, no_target_in_features PASS; rows 20000, split 14000/2000/4000; exact duplicate feature rows 6; missing 0; constant features none; exactly collinear columns 3 (one-hot groups); id AUROC 0.503; max |corr(feature, target)| 0.73381; KS train vs test {'bii': 0.0086}; degenerate targets none.

```
Source: MaleCNS v1.0 (gs://flyem-male-cns/v1.0/...; sha256 in data/README.md; CC-BY 4.0; Berg et al. 2026)
 | Graph: N=166700 neurons (superclass non-null), E=6242118 edges (weight>=5), sign policy plus/plus, graph sha256 d043ac552fd6eb22833eda020224a44497a7b3cd10de4fc79388db8b7be8b952
 | Teacher: pipeline.ts commit e4785726e225e55b1dbdad201758f861f4588ebc, clock frozen at 2026-09-20T00:00:00Z
 | Data: teachers/dti_teacher.jsonl (gen_dti.ts) sha256 2aa26f37b1be93f7af42c4eebfb8f8b03a92839fc433d0e11a0df928936c4b22, run_seed 20260920, 13999/2000/4001 records, split sha256 cb23989c5192e687b635aada79e3a01ee1a645484a16d6b8eb0880cce35aa864, SYNTHETIC, zero PHI
 | Coverage: TEST only, 4001 records, 5 seeds {1,2,3,4,5} of protocol {1..5}; teacher dimensions excluded as degenerate: none (splits/qa_report.json)
 | Feature spec 3d57b09155d4dd58a2c75eba0fa7fe2e84882320f218fb2f4ad07f1a81e52909 | Evaluated 2026-09-22T12:44:41+00:00 | Language-model arms: claude-opus-5 (served as claude-opus-5), adaptive, effort high, max_tokens 16000, temperature not settable under adaptive thinking (not sent), k=3, N=300, prompt sha256 5e7f42957795, prices from claude-api bundled skill, Claude Code 2.1.278 retrieved 2026-09-20; gpt-5 (served as gpt-5-2025-08-07), reasoning_effort high, effort high, max_tokens 16000, temperature 0.0 requested, accepted False, k=3, N=300, prompt sha256 5e7f42957795, prices from developers.openai.com pricing and model pages retrieved 2026-09-20; grok-4 (served as grok-4.3), reasoning_effort high, effort high, max_tokens 16000, temperature 0.0 requested, accepted True, k=3, N=300, prompt sha256 5e7f42957795, prices from docs.x.ai models page and the API's language-models endpoint retrieved 2026-09-20; gemini-3-flash-preview (served as gemini-3-flash-preview), thinking_level high, effort high, max_tokens 16000, temperature 0.0 requested, accepted True, k=3, N=300, prompt sha256 5e7f42957795, prices from ai.google.dev pricing page retrieved 2026-09-20
```

