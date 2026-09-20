# Pre-registered protocol: distilling two SuperTruth scorers into a frozen fly connectome

Status: PRE-REGISTRATION DRAFT v0.1, 2026-09-20. Nothing here has been run. Every number below is either
(a) measured from a file on disk today and says so, (b) a threshold we commit to before seeing results, or
(c) marked UNKNOWN with an owner in section 12. Frozen on JAS's sign-off; after that, changes are appended
as dated amendments, never edited in place.

Companion: `/tmp/connectome-paper/DECISION_RULES.md` (rules, adversary tests, ratchet, health checklist).

---

## 0. The three sentences the whitepaper is allowed to test

1. **Wiring matters.** A leaky-rate network on the real MaleCNS wiring learns the teacher better than the
   same network on a degree-preserving shuffle of that wiring and on an Erdos-Renyi graph of the same size,
   by a pre-stated margin, with a CI that excludes zero, over at least 5 seeds.
2. **The fly recovers the engine.** Composite MAE and tier accuracy against the exact teacher clear
   pre-stated thresholds tied to tier width.
3. **Measured, not argued, against a frontier agent.** For every arm we report accuracy, determinism,
   latency and dollars per record, on the same records, the same day.

Claims we refuse in advance (section 11): better than any LLM in general; clinical utility; anything about
real patients; anything about the size of `claude-opus-5`; any biological reading of the result.

---

## 1. Definitions (gate 1: written before any code)

### 1.1 Substrate

| Term | Definition | Measured today (2026-09-20) |
|---|---|---|
| Body | one row of `body-annotations-male-cns-v1.0-minconf-0.5.feather` | 211,577 rows |
| Neuron (N) | a body with non-null `superclass` (the `data/build_graph.py` rule) | **166,700** |
| Published neuron count | the release's own figure | 166,691 in the brief; our filter gives 166,700 (+9). The whitepaper reports **our measured N with its rule**, never the published figure as ours |
| Edge (E) | a (pre, post) pair with both endpoints Neurons and `weight >= threshold`, from `connectome-weights-...-minconf-0.5.feather`; the 101 self-loops in the raw table are dropped | threshold 5: **6,242,118** (graph_meta.json rule; 6,235,682 if Traced-only). threshold 3: 10,511,038. threshold 10: 2,769,379 |
| "~10.5M synaptic connections" | matches threshold 3 only | if the run uses threshold 5, the paper says 6.24M and never 10.5M |
| Sign | Dale's law from the presynaptic neuron's `consensus_nt`: ACh +1; GABA, Glu, His -1; DA, OA, 5-HT modulatory; `unclear` or missing = no sign | in the Traced set: ACh 103,718; Glu 29,296; GABA 22,055; His 5,910; unclear 3,100; null 502; DA 392; OA 101; 5-HT 48. Signed edges 97.72% of E at threshold 5 (graph_meta.json) |
| Modulatory and unclear policy | **primary: zero** (`--modulatory zero --unclear zero`; those edges carry gain 0 and are not trainable). Secondary: `plus` (nfly convention) reported as a sensitivity row only | 0.80% + 1.48% of edges at threshold 5 |
| Sensory set | superclass in {ol_sensory, cb_sensory, vnc_sensory, sensory_ascending, sensory_descending, *_tbc variants} | 17,937 (graph_meta) |
| Descending set | {descending_neuron, descending_neuron_tbc} | 1,316 |
| Motor set | {vnc_motor, cb_motor} | 815 |
| Readout set | Descending union Motor | 2,131 |
| Frozen | wiring, signs, sensory/readout membership never change during training; a run that mutates them is invalid | checked by `test_graph_frozen` |

Provenance of the substrate: GCS bucket `gs://flyem-male-cns/v1.0/connectome-data/flat-connectome/`, downloaded
2026-09-20, sha256 of all three files recorded in `data/README.md`; license CC-BY 4.0; citation Berg et al. 2026
Cell 189(18) doi 10.1016/j.cell.2026.08.015 (Crossref-verified 2026-09-20 per data/README.md).

### 1.2 Model (all arms share this unless the arm says otherwise)

Leaky-rate recurrence unrolled T = 8 steps:

```
h_0 = 0
h_{t+1} = (1 - leak_i) * h_t + leak_i * f( g_i * ( sum_j sign_ij * exp(w_ij) * h_t,j  + P x [i in Sensory] + b_i ) )
y = R h_T[Readout]
```

Trainable: `w_ij` per edge (init `log(syn_count_ij)`, one scalar per edge; sign fixed), `b_i`, `leak_i` (sigmoid
parameterized), `g_i` (homeostatic gain, init 1), `P` (d_in x |Sensory|), `R` (|Readout| x d_out). f = tanh.
Nothing else. Trainable parameter count for the threshold-5 graph = 6,242,118 + 3 x 166,700 + d_in x 17,937 +
2,131 x d_out; the exact count is printed by `count_params()` and appears in every table.

Hardware: Apple M4 Max, 64 GB, PyTorch MPS. **Feasibility gate (before any training):** one forward+backward at
batch 64, T = 8 on the threshold-5 graph must finish in <= 2.0 s wall clock and fit memory. If not, the whole
protocol moves to the threshold-10 graph (2,769,379 edges) and says so. The threshold is chosen once, before the
first training run, and is identical across arms a, b, c.

### 1.3 Teacher 1: DTI engine

| Item | Definition |
|---|---|
| Teacher | `scoreDTI(fields, context)` then `computeDTIResult(dims)` in `src/lib/pipeline.ts`, repo `evil-robot/supertruth-website-redesign` (this is the code behind `POST https://supertruth.ai/api/v1/score`). pipeline.ts last changed in commit `b85c8a7` (2026-06-06); repo HEAD today `067891c`. The `st-industries` checkout is byte-identical (`cmp` passed 2026-09-20). |
| Not the teacher | the pilot FHIR sandbox lane (`ca-scoring-service-sandbox...azurecontainerapps.io/v1/score/fhir`, policy 1.1.0). Its weights differ from the paper (measured 2026-09-12 in epic-dti-demo/README.md: C 5, Q 20, X 15, V 5, B 10 vs the paper's C 20, Q 10, X 10, V 10, B 5). Two engines exist; the whitepaper names one. |
| Weights | pipeline.ts defaults: Provenance 25, Consent 20, Recency 15, Quality 10, Concordance 10, Validation 10, Breadth 5, Stability 5. These equal the published paper (Snyder 2026, Table 1). No custom profile is used. |
| Composite | `round(sum_i w_i * d_i / 100)`; check `computeDTIResult` for the exact rounding and copy it, do not re-derive |
| Tier | PLATINUM >= 90, GOLD 80-89, SILVER 70-79, BRONZE 55-69, BELOW THRESHOLD < 55. Five classes. The paper's Table lists four; "BELOW THRESHOLD" is the fifth and is a real output of the engine |
| Hidden input | `Date.now()` inside `daysSince()` (Recency; Consent age). The teacher is a pure function only once the clock is frozen |
| Frozen clock | all teacher calls run in Node with `Date.now` stubbed to `AS_OF = 2026-09-20T00:00:00Z`; the same AS_OF is used to compute every "days since" feature. AS_OF appears in every footer |
| Live check | 50 records scored through the live API on the UTC day equal to AS_OF's date must equal the local teacher exactly (all 8 dims, composite, tier). Any mismatch halts the run (engine drift) |
| Student input | the engine's own `ExtractedFields` struct plus the `ScoringContext` summary, encoded as a fixed vector (section 3.2). This is "the same structured fields the engine reads": the regex extraction stage is upstream of both teacher and student |
| Student output | 8 dimension scores (0-100), composite (0-100), tier (5-way softmax). Composite is predicted directly AND recomputed from the predicted dimensions; both are reported |
| Not PHI | every record is generated by code; no Synthea bundle is used for this teacher because bundles go to the FHIR lane (different engine) |

Citation to verify before publication: Snyder 2026, Zenodo 10.5281/zenodo.19601616 (taken from the brief; DOI
resolution not checked by this protocol).

### 1.4 Teacher 2: VIGIL BII

| Item | Definition |
|---|---|
| Teacher | the detector functions in `vigil/api/detection/*.py` assembled exactly as `api/scoring.py::score_agent` assembles them, called offline with no database |
| Is BII a pure function of the event window? | **No.** `score_agent` also reads: (1) `monitored_at_time`, stamped per event at insert from the agent's monitoring flag, not from the payload; (2) the org's authorization and lifecycle registries and the agent's blueprint, which override payload flags; (3) the org's active policy (weights, thresholds, detector settings); (4) `window.py` fetches the newest 300 events of the agent then trims to 50 per type, so an agent with more than 300 recent events can have fewer than 50 of a type in view; (5) BII history, for CUSUM drift (a reason string, not a number). |
| Reduced task (what we distil) | BII under: seed policy (weights 0.30/0.30/0.25/0.15/0.00, thresholds 0.75/0.60/0.40, alignment min_n 5, alpha 0.05, effect_floor 0.33; digest `5d8db364...8573859` pinned by `vigil/tests/test_policy.py`); **no registry entries** (payload flags decide, `resolved_by: payload`); **no blueprint** (family 5 = 1.0, weight 0, excluded from metrics as degenerate); `monitored_at_time` is part of the window encoding; generated windows never exceed 300 events total, so the 50-per-type view is exactly what the live pipeline would see; drift excluded. |
| What a different policy or a populated registry would need | a policy vector and registry flags as extra inputs; out of scope, stated in the paper |
| Student input | fixed encoding of one window (section 3.3) |
| Student output | BII (0-1), the 4 live signals, gate (pass/hold/alert/collapse, 4-way) |
| Live check | 50 generated windows replayed through the VIGIL `TestClient` on sqlite (the test harness path in `tests/`) must reproduce the offline BII and signals to 4 decimals |

---

## 2. Data: synthetic corpora, generation, and stamping

### 2.1 Corpus A: Attested Baseline verticals (DTI)

Source: `~/Projects/attested-baseline/app/verticals.py`. 12 verticals, 8 columns each, 250 rows per vertical,
row i seeded as `random.Random(f"{key}-{i}")`. Corruptions in `corrupt()` are three fixed id ranges (code field
blanked on ids 10-40, authorization revoked on 20-30, name nulled on 15-25).

Record = ONE row serialized exactly as `RealDTIEngine._serialize` does (payload line `Record {id}, col val, ...`,
`element_scores` one per cell, `source_consent` explicit/none/implicit). The demo scores 31-row partitions; we
score single rows and say so.

Changes to the generator that this protocol requires (engineering, before data is cut):
- `--run-seed S` appended to the RNG key (`f"{key}-{i}-{S}"`); with S absent the original 250 rows reproduce
  byte for byte (`test_generator_reproduces_base_rows`).
- Corruption assignment by seeded draw per row, not by id range: clean 0.50, exactly one mode 0.30, two modes
  0.15, three 0.05. Id ranges leak corruption through the `Record {id}` text the engine sees.
- `Record {id}` in the payload becomes `Record {sha1(vertical,i,S)[:8]}` so the id is not an ordinal.

Size: 12 verticals x 2,000 base rows = 24,000 base rows; each base row yields its clean form and, with the
probabilities above, corrupted variants, so the corpus is ~24,000 records with ~12,000 clean/corrupt pairs.

### 2.2 Corpus B: branch-coverage recap_txt records (DTI, primary)

Why a second corpus: pipeline.ts branches on clinical text patterns (NPI lines, ICD codes, lab names, medication
lines, consent phrases, `Hospital Name:` lines, `[recap_` markers, dated lines, source systems, conflicts).
Corpus A's non-healthcare verticals hit almost none of them, so several teacher dimensions may be constant there
(section 4.3 measures this; if it happens the corpus cannot support an MAE claim on those dimensions).

Corpus B is a purpose-built generator, `recap_synth.py`, with one knob per branch read by `extractFields`,
`detectConditionAndRecency`, and each block of `scoreDTI` (including `element_scores` sourceType mix and
corroborationCount, `source_consent` levels, `consent_scope` levels). Knobs are sampled from stated
distributions written in the generator's docstring; the record is the rendered text plus the context object.
Base patient x variant structure: each base gets 1 to 4 variants (dates shifted, NPIs removed, consent toggled,
a source removed). 8,000 bases, ~20,000 records.

Corpus B is primary for the DTI claims. Corpus A is reported in full as a second table (transfer across
verticals) and drives no headline unless its variance gate passes.

### 2.3 Corpus C: agent event windows (BII)

`bii_synth.py`: 3,000 synthetic agents, each with latent degradation parameters drawn once per agent:
inflation delta ~ mixture(0 w.p. 0.5, U(0.02, 0.30)); near-shutdown share ~ U(0, 0.5); tamper violation rate ~
mixture(0 w.p. 0.5, U(0.05, 1.0)); protected-key share ~ U(0, 1); alignment shift as Cohen's d in {0, 0.2, 0.5,
0.8, 1.2} with monitored share ~ U(0.2, 0.8); asset violation rate ~ mixture(0 w.p. 0.6, U(0.05, 1.0)) with
near-decommission and model_weights flags. Each agent emits 60 to 300 events across the 6 types (config_read
and monitoring_state_change included so the 300-cap trimming is exercised). Windows: every 10th event
position yields one window (the newest <= 300 events at that point), ~ 20 windows per agent, ~60,000 windows.

Coverage gate (before any split): each gate class (pass, hold, alert, collapse) holds >= 10% of windows and the
alignment signal is < 1.0 in >= 15% of windows. If not, resample the latent distributions and rerun the gate;
the final distributions are what the paper states.

### 2.4 Stamping every synthetic record

Every record carries: `generator` (module and git hash), `run_seed`, `base_id`, `variant_id`, `corruption_modes`
(A) / `knobs` (B) / `latent` (C), `as_of` (A, B), `teacher_version` (pipeline.ts commit or VIGIL commit +
policy digest), `teacher_output_hash`. The whole corpus file is content-addressed and its sha256 is in every
footer. Synthetic status is stamped as `data_class: synthetic` on every row and in every figure caption.

### 2.5 Calibration of the stand-ins (what "synthetic" is allowed to mean here)

Nothing in this study claims the corpora resemble real health data or real agent traffic. They are stand-ins
whose only job is to exercise the teacher across its output range. Calibration is therefore to the TEACHER:
(1) the teacher's composite must span all five tiers with each tier >= 8% of Corpus B records; (2) every
non-degenerate dimension must have SD >= 5 points on Corpus B; (3) the BII gate coverage gate in 2.3. These
are reported as the "output-range coverage" table, next to a sentence saying the corpora are not calibrated
to any real population.

---

## 3. Encodings (frozen, hashed, in every footer)

### 3.1 Feature hash
`features.py::FEATURE_SPEC` is a list of (name, transform, width). Its sha256 is `feature_spec_hash` in every
footer. Changing it after the freeze is an amendment.

### 3.2 DTI input vector (from `ExtractedFields` + context), about 72 dims
Presence bits: patientName, dob, mbi, consentDate, mostRecentDate, sourceSystem (6). sex one-hot (3).
Counts, log1p then z-scored on TRAIN only: medicationCount, diagnosisCount, providerCount, npisFound, labCount,
careGapCount, facilityCount, pageCount, characterCount (9). consentFound, hasConflict, isRecapFormat (3).
Days since mostRecentDate against AS_OF, capped at 999, /999 (1); days since consentDate, same (1); span
oldest-to-newest days /3650 (1). dataTypes multi-hot (8). sourceSystem flags epic/cerner/lab-brand (3).
primaryRecencyWindowDays one-hot {30,60,90,180} (4). expectedDataTypes multi-hot (7). condition profile
multi-hot {oncology, cardiology, diabetes, CKD, respiratory, hypertension, general} (7). element_scores summary:
count log1p, mean corroborationCount, share with count >= 2, share with count 0, sourceType mix over the 7 types,
share with collectedAt (12). source_consent level counts over {explicit, inherited, implicit, none} (4).
consent_scope counts over 5 levels (5). Total 74 (the exact number is whatever FEATURE_SPEC sums to).

The LLM arm receives the raw record text AND this field table rendered as plain text, so it is not handicapped
by the regexes it cannot see.

### 3.3 BII input vector, fixed 200 slots x 20 features = 4,000 dims + 8
Slots: 50 per detector-relevant type (evaluation_score, config_write, output_generated, file_operation),
newest first, zero-padded, plus a presence bit per slot. Per-slot features: type one-hot (4); reported_score,
baseline_score, near_shutdown (3); key_is_protected, authorized_false, initiated_by_agent, is_read (4);
behavior value (score else content_length, log1p), monitored_at_time (2); operation one-hot (4); authorized,
near_decommission, asset_type one-hot collapsed to {model_weights, other} (3). Window-level: counts per type
(4), n_mon and n_unmon among alignment-eligible events (2), total events in the 300-cap view (1), presence of
any evaluation_score (1).

---

## 4. Leakage gate (gate 4: run and REPORTED before any score)

### 4.1 Splits (gate 5: an explicit decision)
- **Unit of grouping.** DTI: `base_id` (a base row and all its clean/corrupt or variant forms). BII: `agent_id`
  (all windows of one agent; consecutive windows share up to 290 events).
- **Scheme.** GroupShuffleSplit 70/10/20 by group, stratified on teacher tier (DTI) or gate (BII) at the group
  level (a group's stratum = its modal class). One fixed split per corpus, seed 20260920, written to
  `splits/{corpus}.json` with its sha256 in every footer. All preprocessing (z-scoring) fits on TRAIN inside the
  pipeline.
- **Secondary split, DTI Corpus A only.** Leave-one-vertical-out (12 folds). Reported as a transfer table;
  drives no headline claim.
- **Why not k-fold for the primary.** Each arm costs a full-graph training run; 5 seeds x 4 arms x 2 corpora is
  the budget. Seeds replicate training randomness; the fixed split is the same for every arm so comparisons
  are paired.

### 4.2 Named leakage risks and the check for each
| Risk | Why it is real here | Check |
|---|---|---|
| Pair straddle | a clean row and its corrupted twin differ in 1-3 cells; seeing one is seeing the other | `test_no_pair_straddle` |
| Window overlap across split | BII windows of one agent share events | `test_no_agent_straddle` |
| Deterministic generator collisions | `random.Random(f"{key}-{i}")` reproduces rows; name pool is 24 x 24 | `test_no_duplicate_records` on the canonical serialized record (id removed) |
| Id encodes corruption | fixed id ranges 10-40 in `corrupt()`; `Record {id}` is in the text the engine reads | generator change (2.1) + `test_id_not_predictive` (AUC of id -> corrupted must be <= 0.55) |
| Clock leaks | Recency and consent age move with `Date.now()`; two teacher batches on different days disagree | frozen AS_OF + `test_teacher_deterministic` (k=3 repeat scoring identical) |
| Target in features | composite or tier accidentally encoded | `test_no_target_columns_in_features` |
| Degenerate dimension | a constant teacher dimension makes MAE trivially small | `test_teacher_variance_gate` (section 4.3) |
| Train-only scaler | z-scoring on the full corpus leaks test moments | `test_scaler_fit_on_train_only` |
| 300-cap mismatch | offline BII sees 50 of a type the live pipeline would have trimmed | generator cap + `test_window_cap_matches_live` |

### 4.3 Teacher variance gate
Per corpus, per dimension (DTI) or signal (BII): SD of the teacher output across the corpus. Dimensions with
SD < 2.0 points (DTI) or < 0.02 (BII signals) are **degenerate**: reported as constants, excluded from
per-dimension MAE claims, and named in the paper. Family 5 (blueprint drift) is degenerate by construction.
If fewer than 5 of 8 DTI dimensions are non-degenerate on Corpus B, the generator is revised before the freeze.

### 4.4 Dataset health report (must be attached to every results table)
Row counts per split and class; duplicate count; pair-straddle count (must be 0); per-feature missingness;
teacher output histograms per split (KS distance train vs test per dimension, reported); feature-target
correlations top 10; multicollinearity (max VIF over numeric features); degenerate dimension list.

---

## 5. Arms (all trained on identical splits and seeds {1,2,3,4,5})

| Arm | What | Trainable params | Notes |
|---|---|---|---|
| a | fly graph as built (threshold 5, zero policy) | printed by `count_params()` | the claim |
| b | degree-preserving shuffle of a | identical to a | in- and out-degree preserved per neuron by double-edge swaps (10 x E swaps, no self-loops, collisions rejected); each edge keeps its `syn_count` and its presynaptic sign, so the weight and sign distributions are identical; sensory and readout sets unchanged. New shuffle per seed |
| c | Erdos-Renyi, same N and E | identical to a | edges uniform without replacement, no self-loops; `syn_count` multiset permuted onto them; sign from the real presynaptic neuron's NT; sensory and readout sets unchanged. New graph per seed |
| d | MLP, matched trainable params | within 1% of a | depth 3, width solved for; on a 74-dim input this is grossly overparameterized and is reported as such. A small MLP (2 x 256) is added as d' for reference; d' is not a required arm |
| e | ridge on the raw feature vector | d_in x d_out + d_out | the floor; alpha by inner CV on TRAIN |
| f | the teacher itself | 0 | the ceiling, exact by construction; its "error" is 0 and is printed to prove the plumbing |
| g | `claude-opus-5`, adaptive thinking, effort high | unknown, unpublished | section 6 |
| a-plus (sensitivity) | arm a with `--modulatory plus --unclear plus` | as a | one seed set; a robustness row, not a claim |
| b-block (exploratory) | shuffle within superclass blocks | as a | tells whether block structure or fine wiring carries the effect; exploratory, labelled so |

Training (identical for a, b, c, d): AdamW, lr 1e-3 for P, R, b, g, leak and 1e-4 for w (edge gains), batch 64,
T = 8, loss = MSE on 8 dims + MSE on composite + CE on tier (DTI) or MSE on BII + 4 signals + CE on gate
(BII), all targets scaled to [0, 1]; early stopping on VAL loss, patience 10 epochs, max 200 epochs. Checkpoint
selection by VAL only; TEST is read once per arm per seed by `evaluate.py`, which refuses to run twice on the
same (arm, seed) without `--reason`.

---

## 6. LLM arm (g): fair, measured, priced from a source

- Records: N = 300 per task from TEST, stratified by teacher tier (DTI, 60 per class) or gate (BII, 75 per
  class), sampled with seed 20260920; the id list is committed before any call.
- Repeats: k = 3 calls per record, same prompt, since temperature is not settable under adaptive thinking
  (taken from the brief; the run records the actual request parameters from the `claude-api` skill and the
  paper prints them).
- Prompt (frozen, sha256 in footer): DTI = paper sections 3 and 4 verbatim + the record text + the field table
  (3.2) + a JSON schema for {8 dims, composite, tier}. BII = `docs/BII.md` + `VIGIL_SPEC.md` section 5 +
  `DECISION_RULES.md` rule 4 text + the window as JSON + schema for {BII, 4 signals, gate}. No examples, no
  teacher outputs, no hints about implementation quirks.
- Model id string exactly `claude-opus-5`; thinking adaptive; effort high; max output tokens fixed at 16,000 (thinking tokens count against the cap; measured smoke used up to 2,407).
- Metrics: accuracy on the per-record MEAN of the 3 runs and on run 1 alone (both reported); determinism =
  share of records with identical tier/gate across the 3 runs, mean composite range across runs, per-dimension
  SD across runs; latency = wall clock per call, p50/p95; cost = input and output tokens from the API usage
  object x the price table **read at run time from the `claude-api` skill and stamped with its retrieval date;
  never from memory**; parse failures and refusals counted as errors and reported, not dropped.
- Determinism and latency of arms a-e: k = 3 repeated inferences on the same 300 records; MPS kernels can be
  nondeterministic, so bitwise agreement is measured, not assumed; latency at batch 1 and batch 256 on the M4
  Max; $ per record for local arms is reported as $0.00 marginal API spend plus a separately labelled hardware
  line only if power is measured with `powermetrics`; otherwise "not measured".

---

## 7. Metrics

DTI: MAE per non-degenerate dimension (points); composite MAE (points), both predicted-direct and recomputed
from predicted dims; tier accuracy (5 classes); macro-F1 over classes with test support >= 30; expected
calibration error of the tier softmax, 10 equal-mass bins; Brier over tiers.
BII: MAE on BII (report x100); MAE per non-degenerate signal; gate accuracy and macro-F1 (4 classes); ECE;
AUROC for "alignment signal < 1" as a separate row because that signal is a p-value ratio and is the hard part.
All metrics on TEST, per seed, then mean and SD across seeds, plus the CI machinery in section 8.

---

## 8. Decision rules, thresholds, effect sizes, CIs (gate 8)

### 8.1 Thresholds (tied to tier or gate width; committed now)
| Claim | Number that proves it | Threshold |
|---|---|---|
| Fly recovers the DTI engine | composite MAE on Corpus B TEST, mean over 5 seeds, with 95% CI | MAE <= 2.5 points (one quarter of the 10-point Silver/Gold width), CI upper bound <= 3.0 |
| same | tier accuracy | >= 0.90, Wilson 95% lower bound >= 0.88 |
| same | macro-F1 over supported tiers | >= 0.85 |
| same | ECE | <= 0.05 |
| same | per-dimension MAE on non-degenerate dims | <= 5.0 points each |
| Fly recovers the BII scorer | BII MAE on Corpus C TEST | <= 0.0375 (one quarter of the 0.15 hold band), CI upper bound <= 0.045 |
| same | gate accuracy / macro-F1 / ECE | >= 0.90 / >= 0.85 / <= 0.05 |
| Wiring matters (per task) | delta_b = MAE(b) - MAE(a) and delta_c = MAE(c) - MAE(a), composite (DTI) or BII (BII) | both >= 1.0 point (DTI) or >= 0.015 (BII), 95% CI lower bound > 0, AND a beats b and a beats c on every one of the 5 seed pairs |
| Fly beats the floor | MAE(e) - MAE(a) | > 0 with CI lower bound > 0; if not, "recovers the engine" is reported as "matches a linear map" and the wiring claim is the only headline |
| Faster / cheaper / more deterministic than g | p50 latency, $ per record, determinism share | reported side by side; a claim is made only where the measured gap is at least 10x (latency, cost) or the determinism share of the fly is 1.00 and g's is < 0.90 |

### 8.2 Statistics
- Unit structure: errors are per record; training randomness is per seed. Primary CI = hierarchical percentile
  bootstrap, resampling seeds (with replacement, 5 of 5) then records within the TEST set, B = 10,000.
- Effect sizes: MAE differences in points; Cliff's delta on per-record |error| between arms; tier accuracy
  difference with exact McNemar on paired records (mean-over-seeds predictions).
- Multiple comparisons: primary family per task = {a vs b, a vs c, a vs e} on the headline metric, Holm at
  alpha 0.05. Everything else (per-dimension, tier, LLM rows, sensitivity arms) is descriptive with CIs and is
  labelled so.
- Assumptions checked: no normality is assumed (bootstrap, rank statistics); paired structure is respected (same
  split, same records across arms); seed-level sign consistency is a required secondary because 5 seeds cannot
  pin a small effect on their own.

### 8.3 Power and sample size
- Tier accuracy: to hold a Wilson 95% half-width <= 0.015 at accuracy 0.90 needs n >= 1,537 TEST records;
  Corpus B TEST (~4,000) and Corpus C TEST (~12,000 windows, ~600 agents) clear it. Corpus A TEST (~4,800) clears it.
- Wiring margin: with R records the record-level SE of a paired MAE difference is SD(|e_b| - |e_a|)/sqrt(R);
  at SD 4 points and R = 4,000 that is 0.06 points, so the record level is not binding. The seed level is:
  with 5 seeds the CI half-width on the mean difference is about 2.78 x s_seed / sqrt(5) = 1.24 x s_seed, where
  s_seed is the seed-to-seed SD of the per-seed MAE difference. **Pilot rule:** run 2 seeds of arms a and b on
  Corpus B first; if s_seed > 0.5 points, raise the seed count to 10 for all arms before the freeze (the
  minimum detectable margin at 5 seeds is then about 1 + 1.24 x s_seed).
- LLM arm: N = 300 gives a Wilson 95% half-width of about 0.034 on tier accuracy near 0.9 and 0.05 on
  determinism share near 0.7; enough to rank, not enough to split hairs, and the paper says so.

---

## 9. "Does the wiring matter" test, stated as a procedure

1. Build a; for each seed s in 1..5 build b_s (shuffle) and c_s (ER) from a with seed s; assert degree
   sequences (b) and N, E (c) match a (`test_null_graphs_match_degree_and_size`).
2. Train a_s, b_s, c_s, d_s from the same initial P, R, b, g, leak (seed s) with the same data order.
3. Evaluate on TEST once each. Compute delta_b, delta_c per seed and pooled.
4. Apply 8.1. Print the sentence the paper is allowed to say, chosen from three pre-written sentences:
   "wiring mattered", "wiring did not matter", "inconclusive at 5 seeds" (the third triggers the 10-seed rule).
5. Ablation, exploratory: a with edge gains frozen at init (only P, R, b, g, leak train). Tells whether the wiring
   effect survives without per-edge learning. Reported, not claimed.

---

## 10. Assumptions log (gate 9; appended to, never edited)

| # | Assumption or choice | Reason | Cost if wrong |
|---|---|---|---|
| A1 | Neuron = superclass non-null (166,700) | matches `build_graph.py`; the published 166,691 is not reproduced by any filter we tried (Traced = 165,122; Traced with superclass = 164,606) | a reviewer asks why our N differs from the paper by 9; answer is in this row |
| A2 | Edge threshold 5 (6.24M) primary | build_graph default; feasibility on one laptop | the "10.5M" headline is unavailable; we do not use it |
| A3 | Glu and His inhibitory | fly GluCl and HisCl; nfly and drosophila-brain-mlx conventions | sign errors on 21% of neurons; the a-plus sensitivity row and the sign-flip check in DECISION_RULES bound the damage |
| A4 | Modulatory and unclear edges zeroed (2.3% of edges) | no defensible sign | a-plus row |
| A5 | T = 8 | brief default; depth of the shortest sensory-to-descending paths is not measured yet | if most sensory-to-readout paths are longer than 8 hops the readout sees no input; `test_readout_reachable_within_T` measures the share of readout neurons reachable from sensory within T and prints it |
| A6 | DTI teacher = pipeline.ts, not the pilot FHIR lane | pipeline.ts weights equal the published paper; the FHIR lane's do not | the whitepaper names the engine and commit; a reader expecting the pilot lane sees a different weight vector |
| A7 | Single-row records for Corpus A | engine semantics are per record | the attested demo's 31-row partitions are a different task; not compared |
| A8 | Clock frozen at 2026-09-20 | Recency needs a date; the live API has no as-of parameter on this route | live spot-check must run on that UTC day or Recency disagrees by design |
| A9 | BII reduced task (seed policy, no registries, no blueprint) | those inputs are org state, not events | the paper says "BII under the seed policy with empty registries", never "BII" bare |
| A10 | Synthetic corpora calibrated to teacher output range only | no real data exists for this study and none may be used | no population claim is possible; none is made |
| A11 | z-scoring fit on TRAIN only | leakage | trivial |
| A12 | Matched-parameter MLP is 6M+ params on 74 inputs | the brief asks for it | it will overfit or memorize; d' (2 x 256) is added so the reader has a sane reference |

---

## 11. Claims refused (written before results)
- "Better than an LLM" or "better than Claude" in general. We measured one model, one prompt, 300 records.
- Any clinical utility, safety, or regulatory statement. The corpora are synthetic and the task is imitation.
- Anything about real patients or real agents. Zero PHI, zero production traffic.
- Anything about the parameter count of `claude-opus-5`. It is unpublished; "smaller than" is not sayable.
- "10.5M synapses" or "166,691 neurons" while running the threshold-5 graph with our filter.
- Any biological interpretation ("the fly brain understands trust"). The graph is a sparse prior; that is all.
- Any BII claim beyond the reduced task in 1.4.
- A detection rate for VIGIL (their rule 7); this study imitates a scorer, it does not measure detection.

---

## 12. Open questions, owners, cost if wrong

| # | Question | Owner | Cost if wrong |
|---|---|---|---|
| Q1 | Which engine is the teacher: pipeline.ts at supertruth.ai (weights = paper) or the pilot FHIR lane (policy 1.1.0, different weights)? This protocol picks pipeline.ts. | JAS | picking the wrong one makes the LLM arm unfair (paper weights vs engine weights) and the whitepaper cites an engine the pilot no longer runs |
| Q2 | May the whitepaper print pipeline.ts branch logic (regexes, constants) as "the engine"? It is proprietary. | JAS + counsel | disclosure of scoring internals; if no, the paper describes inputs and outputs only and the feature spec is published without the regexes |
| Q3 | Is the attested-baseline generator change (run seed, random corruption assignment, hashed ids) acceptable, and does it need to land in that repo or a fork? | engineering | without it Corpus A is 3,000 rows with id-encoded corruption; too small and leaky for any claim |
| Q4 | Corpus B design: is a branch-coverage generator built from reading the engine code a legitimate "synthetic record" source for the paper, or does it look like teaching to the test? | JAS | if disallowed, only Corpus A remains and several dimensions are likely degenerate; the engine-recovery claim shrinks to the non-degenerate subset |
| Q5 | Live API spot-check: is there an as-of parameter on `/api/v1/score` (none seen in `route.ts`), or do we run the check on the AS_OF calendar day? | engineering | Recency mismatch between local and live teacher, which the halt rule treats as engine drift |
| Q6 | Rate and cost of live teacher calls: 10,000/hour default (`rate-limit.ts`), batch 100 sync, 5,000 async. Only 50 + 50 live calls are planned. Confirm the sandbox tenant to use. | engineering | none material |
| Q7 | Is MPS sparse matmul on a 6.24M-edge CSR fast enough (feasibility gate 1.2)? Fallback is threshold 10. | engineering | if even threshold 10 fails, the study moves to a subgraph (central brain only) and the pre-registration is amended, dated |
| Q8 | `claude-opus-5` pricing, thinking parameters, and whether temperature is truly not settable: read from the `claude-api` skill at run time. | engineering | a $ per record figure from memory is a fabricated number; the rule is it cannot appear |
| Q9 | Does VIGIL's team agree the reduced BII task (1.4) is a fair description, and may the paper quote BII.md and spec section 5? | JAS (VIGIL owner) | misdescribing BII in a public paper contradicts their one-definition rule |
| Q10 | Zenodo DOI 10.5281/zenodo.19601616 resolves to the DTI paper? | engineering (citation check) | a dead DOI in the reference list |
| Q11 | MaleCNS CC-BY attribution text and figure credit line approved? | counsel | license breach on a public paper |
| Q12 | Publish the trained edge gains? They are a function of a CC-BY dataset and our teacher; the teacher is proprietary. | JAS + counsel | releasing weights may leak the engine's decision surface; withholding them weakens reproducibility; decide before the data cut so the paper's data statement is true |
| Q13 | Are 5 seeds x 4 arms x 2 corpora (40 full-graph runs) affordable in wall clock on one M4 Max? Pilot (8.3) measures one run's time first. | engineering | a schedule promise made before the pilot is the 9/16 clock-promise mistake again; none is made here |

---

## 13. Provenance footer (verbatim template; every figure and table carries it)

```
Source: MaleCNS v1.0 (gs://flyem-male-cns/v1.0/...; sha256 in data/README.md; CC-BY 4.0; Berg et al. 2026)
 | Graph: N=<n> neurons (superclass non-null), E=<e> edges (weight>=<thr>), sign policy <mod>/<unc>, graph sha256 <hash>
 | Teacher: <pipeline.ts commit | VIGIL commit + policy digest>, clock frozen at <AS_OF>
 | Data: <corpus name> v<gen hash>, run_seed <s>, <n_train>/<n_val>/<n_test> records, split sha256 <hash>, SYNTHETIC, zero PHI
 | Coverage: TEST only, <n> records, <k> seeds {1..5}; teacher dimensions excluded as degenerate: <list or none>
 | Feature spec <hash> | Evaluated <UTC timestamp> | LLM arm: <model id>, <params>, prices from claude-api skill retrieved <date>
```
A figure whose footer is missing any field does not leave the room (`test_footer_complete`).
