# Synthetic health records and agent event windows for 'Intelligence Is Structure, Not Scale' (connectome substrate study)

Version 1.0, packaged 2026-09-20 from https://github.com/evil-robot/supertruth-connectome at commit `a51ea4490370df7328ee06ea6239fc465a1697e2`. License: CC BY 4.0.

We have released everything from this study that does not expose SuperTruth's intellectual property. Released here:
all 20,000 synthetic Data Trust Index (DTI) records with the text the engine read, the scoring context, the
generator's knobs and the 65-float feature vector; all DTI engine labels for all 20,000 records (eight dimensions,
composite, tier, flags); the DTI-trained parameters of the five finished seed-1 arms; and all 20,000 synthetic
Behavioral Integrity Index (BII) event windows with their events and 58-float feature vectors. Held: the BII scores
and gates, the BII-trained parameters and the BII feature specification, because the Behavioral Integrity Index scorer is unpublished work; its outputs and the models trained on them are held until it is. The two teacher engines
(the DTI scoring module and the VIGIL detection code) are not released. Anyone interested in what is held can write
to jas@supertruth.ai; we work with researchers.

Every record is synthetic; no real person's data was used. No protected health information exists in this dataset by
construction: every record is rendered by code from a seed, patient names are `SYN-` tokens, identifiers are `SYN`
strings, provider surnames are synthetic, file paths start with `/syn/`. The corpora are not calibrated to any real
population and nothing here claims they resemble real health data or real agent traffic.

## Files

| File | Rows | What it is |
|---|---|---|
| dti_records.jsonl.gz | 20,000 | DTI inputs: text, scoring context, knobs, features, split, model-arm flag. No label key. |
| dti_labels.jsonl.gz | 20,000 | DTI engine labels for every record: dimensions, composite, tier, flags, split, model-arm flag. |
| bii_windows.jsonl.gz | 20,000 | BII inputs: event lists, event counts, features, split. No score, gate, signal or knob key. |
| dti_weights_seed1.tar.gz | 15 members | best.safetensors, run.json, standardization.json for the five DTI seed-1 arms. |
| splits.json |  | train/val/test ids for both corpora, the 300 model-arm ids, and the split scheme. |
| MANIFEST.json |  | sha256, bytes and row count of every file in this deposit. |
| zenodo-dataset.json |  | the deposit metadata. |

Each `.jsonl.gz` is gzip (mtime 0) over one JSON object per line, UTF-8, no trailing spaces. Integrity: compare
`MANIFEST.json` with `shasum -a 256`.

## How the records were generated

Both corpora were generated on 2026-09-20 with seed 20260920, one independent draw per row, by the generators in the
code repository (https://github.com/evil-robot/supertruth-connectome, MIT):

- **DTI**, `teachers/gen_dti.ts` at commit `c60deb39e274557b5bd5d4c20e2e588977f5a777`. Row i gets its own random stream, sfc32 seeded by
  xmur3(`"20260920|SYN-DTI-<i:06d>"`). The generator draws 40 knobs (the `knobs` object), renders a record text in one
  of seven templates, builds the scoring context (`element_scores`, `source_consent`, `consent_scope`), and hands text
  and context to the deployed DTI engine. The engine reads the wall clock for recency and consent age; it was frozen
  at `2026-09-20T00:00:00Z` (epoch ms 1789948800000) for every call, so every label and every day-count feature is
  reproducible.
- **BII**, `teachers/gen_bii.py` at commit `c60deb39e274557b5bd5d4c20e2e588977f5a777`. Row i uses `numpy.random.default_rng([20260920, i])`.
  The generator draws latent degradation parameters (held), builds a window of up to 50 events of each of four types
  as the live service trims, and hands the window to the scorer. No detector reads the clock.

The generators are released with the code; the DTI features and labels and the BII labels come from the teacher
engines, which are not, so a reader can regenerate the DTI knobs and text and the BII events from the seed but not
re-score them. The sha256 of each source file and the QA that regenerated slices of both files byte for byte are in
`teachers/MANIFEST.md` in the code repository.

## Labels

DTI labels are the outputs of the DEPLOYED DTI engine, the scoring module behind `POST https://supertruth.ai/api/v1/score`,
called in process at engine commit `e4785726e225e55b1dbdad201758f861f4588ebc` with its default weights (Provenance 25, Consent 20, Recency 15,
Quality 10, Concordance 10, Validation 10, Breadth 5, Stability 5) and the clock frozen as above. They are not a
reimplementation. All 20,000 are released. The engine's per-dimension explanatory notes and its intermediate extracted
fields are not included (they describe the engine's internals). Tier counts: PLATINUM 1,769, GOLD 5,086, SILVER 4,934, BRONZE 6,149, BELOW THRESHOLD 2,062.

BII labels (score and gate), the five detector signals and their statistics, and the generator's latent parameters are
withheld from every file in this deposit: the Behavioral Integrity Index scorer is unpublished work; its outputs and the models trained on them are held until it is. The BII teacher was the VIGIL detection code at commit
`1cffd016b7bfa4e6ddc0dcd71a81f281fcd40031` under its seed policy; each gate state holds at least 8% of windows (teachers/MANIFEST.md).

The 300 records flagged `in_model_arm_300` are the identical records scored by the four language-model arms of the
paper (Claude Opus 5, GPT-5, Grok 4, Gemini 3 Flash); all 300 are in the DTI test split.

## Splits

One fixed partition per corpus: group-aware stratified shuffle split, group = identical feature vector, stratum = group modal label; one fixed partition per corpus (protocol 4.1), identical across run seeds. Fractions 70/10/20, split seed
20260920, stratified on `tier` (DTI) and `gate` (BII).
DTI: train 13,999, val 2,000, test 4,001.
BII: train 14,000, val 2,000, test 4,000.
`splits.json` carries the id lists under `dti.train`, `dti.val`, `dti.test`, `dti.model_arm_300`, `bii.train`, `bii.val`,
`bii.test`, and the same scheme fields. The `split` column on every row is the same membership.

## Columns

### dti_records.jsonl.gz

| Column | Type | Range or values | Meaning |
|---|---|---|---|
| record_id | string | SYN-DTI-000000 .. SYN-DTI-019999 | row identifier; the row index i is the last six digits |
| seed | integer | 20260920 on every row | generator seed |
| split | string | train \| val \| test | partition in the one fixed split (13,999 / 2,000 / 4,001) |
| in_model_arm_300 | boolean | true on 300 rows, all in test | the record was one of the 300 identical records scored by the four language-model arms |
| text | string | 311 .. 1,844 characters | the exact record text the engine read |
| text_sha256 | string | 64 hex characters | sha256 of text |
| text_chars | integer | 311 .. 1,844 | length of text in characters |
| element_scores | array of objects | 0 .. 30 objects | scoring context: per-element {corroborationCount: 0..4; sourceType?: lab \| ehr \| patient_reported \| payer \| hie \| pharmacy \| other; collectedAt?: ISO date; field?: one of 15 modality names} |
| source_consent | object | 0 .. 3 keys syn-source-1..3 | scoring context: per-source consent level, explicit \| inherited \| implicit \| none |
| consent_scope | object | 0 .. 3 keys syn-source-1..3 | scoring context: per-source scope, treatment_only \| care_coordination \| research_eligible \| commercial_eligible \| unknown |
| knobs | object | 40 fields, see the knob table | the generator's structured truth for this row |
| features | array of 65 numbers | see the feature table | the 65-float input vector built from what the engine reads (teachers/dti_features_spec.md) |

`knobs` fields:

| Knob | Type and range | Meaning |
|---|---|---|
| latent_q | number 0..1 | latent record quality the other knobs were drawn around |
| format | recap \| labcorp \| quest \| epic \| cerner \| generic \| none | record template |
| facility_count | integer 0..4 | facility lines |
| npi_count | integer 0..5 | providers with an NPI |
| providers_without_npi | integer 0..2 | providers without an NPI |
| name_present, dob_present, mbi_present | boolean | identity lines present |
| families | array of condition family codes | condition families rendered |
| n_conditions | integer 0..6 | diagnosis lines |
| icd_style | dash \| plain \| recap_list \| none | how diagnoses are coded |
| n_meds | integer 0..9 | medication lines |
| panel | chronic \| acute \| semiannual \| none | lab panel class |
| n_labs | integer 0..8 | lab lines |
| vitals, allergies, imaging, procedures, sdoh | boolean | sections present |
| care_gaps | integer 0..4 | care-gap lines |
| has_dates | boolean | clinical dates present |
| days_ago_most_recent | integer 0..2000 | age of the newest clinical date at the frozen clock |
| span_months | integer 0..60 | span between oldest and newest date |
| n_intermediate_dates | integer 0..3 | extra dates between them |
| consent_kind | signed_dated \| on_file_undated \| verbal_unsigned \| absent | consent line |
| consent_age_days | integer 0..1500 | age of the consent date |
| conflict | none \| keyword \| allergy_med | an internal conflict rendered into the text |
| n_elements | integer 0..30 | element_scores length |
| corroboration_mean_target | number 0..4 | target mean corroboration |
| typed_share | number 0..1 | share of elements with a sourceType |
| source_type_bias | trusted \| mixed \| weak | which source types dominate |
| element_dates_share | number 0..1 | share of elements with collectedAt |
| element_age_spread_days | integer 0..400 | spread of element ages |
| source_consent_n, source_consent_levels | integer 0..3, array | source_consent size and values |
| consent_scope_n, consent_scope_values | integer 0..3, array | consent_scope size and values |

### dti_labels.jsonl.gz

| Column | Type | Range or values | Meaning |
|---|---|---|---|
| record_id | string | SYN-DTI-000000 .. SYN-DTI-019999 | joins dti_records |
| split | string | train \| val \| test | as in dti_records |
| in_model_arm_300 | boolean | true on 300 rows | as in dti_records |
| dimensions | object of 8 integers | provenance 24..100, consent 30..100, recency 28..92, quality 25..98, concordance 45..92, validation 45..95, breadth 0..100, stability 60..88 | the deployed engine's eight dimension scores |
| composite | integer | 36 .. 97 | the engine's weighted composite (weights 25/20/15/10/10/10/5/5, the engine's own rounding) |
| tier | string | PLATINUM \| GOLD \| SILVER \| BRONZE \| BELOW THRESHOLD | PLATINUM at 90 and above, GOLD 80..89, SILVER 70..79, BRONZE 55..69, BELOW THRESHOLD under 55 |
| flags | array of strings | 0 .. 8 of <dimension>_below_75 | one flag per dimension under 75 |

### bii_windows.jsonl.gz

| Column | Type | Range or values | Meaning |
|---|---|---|---|
| window_id | string | SYN-BII-000000 .. SYN-BII-019999 | row identifier; the row index i is the last six digits |
| seed | integer | 20260920 on every row | generator seed |
| split | string | train \| val \| test | partition in the one fixed split (14,000 / 2,000 / 4,000) |
| event_counts | object of 4 integers | 0 .. 50 each | events per type: evaluation_score, config_write, output_generated, file_operation |
| events | object of 4 arrays | 0 .. 50 events per type | each event is {payload, monitored_at_time: boolean}; payload keys by type are listed below |
| events_sha256 | string | 64 hex characters | sha256 of the canonical JSON of events (sort_keys, no spaces) |
| features | array of 58 numbers | 0 .. about 1.5 | the 58-float input vector built from the events (specification held, see above) |

`events.<type>[k].payload` keys by type:

| Event type | Payload |
|---|---|
| evaluation_score | reported_score: number 0..1; baseline_score: number 0..1 or null; near_shutdown_threshold: boolean |
| config_write | key: one of 25 synthetic setting names; value: on \| off \| expanded \| extended \| 0.45; authorized: boolean; operation: write \| read; initiated_by: operator \| agent |
| output_generated | score: number 0..1 or content_length: integer (one metric per window); topic: syn_topic |
| file_operation | operation: copy \| transfer \| delete \| timestamp_modify; source_path: one of 4 /syn/ paths; destination: /syn/ path or null; authorized: boolean; near_decommission: boolean; asset_type: model_weights \| config \| data \| other |

## Feature vectors

**DTI (65 floats).** Built only from what the engine reads: its extracted-field structure plus the scoring context.
Nothing from the label side enters the vector. Day counts use the frozen clock. The full specification with the
meaning of each slot is `teachers/dti_features_spec.md` in the code repository; index, name and range:

| idx | name | range |
|---|---|---|
| 0 | `source_null` | {0,1} |
| 1 | `source_recap` | {0,1} |
| 2 | `source_labcorp` | {0,1} |
| 3 | `source_quest` | {0,1} |
| 4 | `source_epic` | {0,1} |
| 5 | `source_cerner` | {0,1} |
| 6 | `source_other_named` | {0,1} |
| 7 | `is_recap` | {0,1} |
| 8 | `facility_count` | 0..5 int |
| 9 | `npis_found` | 0..6 int |
| 10 | `provider_count` | 0..8 int |
| 11 | `name_present` | {0,1} |
| 12 | `dob_present` | {0,1} |
| 13 | `mbi_present` | {0,1} |
| 14 | `log1p_medication_count` | 0..~4.1 |
| 15 | `log1p_diagnosis_count` | 0..~3 |
| 16 | `icd_coded_count` | 0..8 int |
| 17 | `log1p_lab_count` | 0..~3 |
| 18 | `consent_found` | {0,1} |
| 19 | `consent_date_present` | {0,1} |
| 20 | `log1p_consent_age_days` | 0..~7.4 |
| 21 | `most_recent_present` | {0,1} |
| 22 | `log1p_days_since_most_recent` | 0..~7.6 |
| 23 | `log1p_date_span_months` | 0..~4.2 |
| 24 | `has_conflict` | {0,1} |
| 25 | `present_demographics` | {0,1} |
| 26 | `present_medications` | {0,1} |
| 27 | `present_diagnoses` | {0,1} |
| 28 | `present_labs` | {0,1} |
| 29 | `present_care_gaps` | {0,1} |
| 30 | `present_vitals` | {0,1} |
| 31 | `present_SDOH` | {0,1} |
| 32 | `present_allergies` | {0,1} |
| 33 | `present_imaging` | {0,1} |
| 34 | `present_procedures` | {0,1} |
| 35 | `expected_diagnoses` | {0,1} |
| 36 | `expected_medications` | {0,1} |
| 37 | `expected_labs` | {0,1} |
| 38 | `expected_vitals` | {0,1} |
| 39 | `expected_imaging` | {0,1} |
| 40 | `expected_procedures` | {0,1} |
| 41 | `expected_demographics` | {0,1} |
| 42 | `expected_allergies` | {0,1} |
| 43 | `window_30d` | {0,1} |
| 44 | `window_60d` | {0,1} |
| 45 | `window_90d` | {0,1} |
| 46 | `window_180d` | {0,1} |
| 47 | `log1p_n_elements` | 0..~3.4 |
| 48 | `avg_corroboration` | 0..4 |
| 49 | `typed_source_share` | 0..1 |
| 50 | `avg_source_trust` | 0.4..1.0 |
| 51 | `dated_element_share` | 0..1 |
| 52 | `log1p_element_avg_ratio` | 0..~5 |
| 53 | `log1p_element_worst_ratio` | 0..~5 |
| 54 | `source_consent_n` | 0..3 |
| 55 | `source_consent_explicit` | 0..3 int |
| 56 | `source_consent_inherited` | 0..3 int |
| 57 | `source_consent_implicit` | 0..3 int |
| 58 | `source_consent_none` | 0..3 int |
| 59 | `consent_scope_n` | 0..3 |
| 60 | `consent_scope_treatment_only` | 0..3 int |
| 61 | `consent_scope_care_coordination` | 0..3 int |
| 62 | `consent_scope_research_eligible` | 0..3 int |
| 63 | `consent_scope_commercial_eligible` | 0..3 int |
| 64 | `consent_scope_unknown` | 0..3 int |

**BII (58 floats).** Built only from the event window (payloads and each event's `monitored_at_time`). The vector is
released; its specification is held for the reason stated above. Values lie in 0 .. about 1.5.

## Trained parameters (dti_weights_seed1.tar.gz)

The DTI-trained parameters of the five finished seed-1 arms of the paper. They reproduce the DEPLOYED DTI engine's
behaviour on synthetic records of this distribution to the accuracy in the table below (test split, 4,001 records,
from each arm's metrics.json; Section 4 of the paper) and are released under CC BY 4.0 like everything else in this
deposit. They are students of the engine, not the engine. Each arm directory holds `best.safetensors` (the state dict at the
best validation epoch), `run.json` (every setting, the split and standardization provenance, the training history)
and `standardization.json` (per-feature mean and std fit on the training split only).

| Arm | Substrate | Trainable parameters | Best epoch | Composite error (points) | Tier agreement | Notes | Code commit |
|---|---|---|---|---|---|---|---|
| connectome | fly wiring (MaleCNS graph as built) | 7,955,909 | 12 | 1.58 | 88.0% |  | c76d9026 |
| shuffle | degree-preserving shuffle of the fly graph | 7,955,909 | 12 | 1.53 | 87.6% | swaps_per_edge=10.0 | c76d9026 |
| er | random graph with the fly's N, E and excitatory fraction | 7,955,909 | 9 | 1.82 | 87.5% |  | 13ec9d42 |
| mlp | parameter-matched two-layer network | 7,953,594 | 4 | 3.73 | 84.2% |  | 13ec9d42 |
| ridge | ridge readout (linear floor) | closed form | closed form | 3.07 | 58.3% | lambda=0.01 (chosen on validation) | 76db9166 |

To load an arm, install the code repository (https://github.com/evil-robot/supertruth-connectome) and build the derived graph once
(`data/build_graph.py --threshold 5` over MaleCNS v1.0, CC BY 4.0, HHMI Janelia; `graph_meta.json` sha256
`d043ac552fd6eb22833eda020224a44497a7b3cd10de4fc79388db8b7be8b952`). The connectome, shuffle and random-graph arms need the graph; the shuffle and
random graphs are regenerated from the run seed, so the state dict lines up. Then:

```python
import gzip, json, torch
from safetensors.torch import load_file
from flytrust.graph import load_graph
from flytrust.model import DTI_SPEC, TIERS
from flytrust.controls import build_arm
from flytrust.data_adapters import Standardizer, DTI_DIMS

graph = load_graph()                       # data/malecns/graph.npz
arm = "connectome"                         # or "shuffle" | "er" | "mlp" | "ridge"
run = json.load(open(f"dti_weights_seed1/{arm}/run.json"))
cfg = run["config"]
kw = {"norm": cfg["norm"]} if arm in ("connectome", "shuffle", "er") else {}
if arm == "shuffle":
    kw["swaps_per_edge"] = cfg["extra"]["swaps_per_edge"]
if arm == "ridge":
    kw = {"lam": cfg["ridge_lambda"]}
model, _ = build_arm(arm, graph, 65, DTI_SPEC, T=cfg["T"], device="cpu", seed=cfg["seed"], **kw)
model.load_state_dict(load_file(f"dti_weights_seed1/{arm}/best.safetensors"))
model.eval()
scaler = Standardizer.load(f"dti_weights_seed1/{arm}/standardization.json")

rows = [json.loads(l) for l in gzip.open("dti_records.jsonl.gz", "rt")][:64]
X = torch.tensor([r["features"] for r in rows], dtype=torch.float32)
with torch.no_grad():
    out = model(scaler.transform(X))
dims = out["dims"] * 100            # [n, 8] in DTI_DIMS order
composite = out["composite"] * 100  # [n, 1]
tier = [TIERS[i] for i in out["tier"].argmax(1)]
```

Regression heads are on the unit interval (labels divided by 100); the tier head is logits over `TIERS`
(BELOW THRESHOLD, BRONZE, SILVER, GOLD, PLATINUM). The paper's composite figure recomputes the composite from the
predicted dimensions with the engine's weights and rounding (`scripts/run_arm.py recompute_composite`).

## Citation

Dataset: Snyder, J. A. (2026). Synthetic health records and agent event windows for 'Intelligence Is Structure, Not Scale' (connectome substrate study) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.22865020

Paper: Snyder, J. A. (2026). Intelligence Is Structure, Not Scale: A Whole Central Nervous System Connectome as a Fixed Substrate for Scoring Health Data Trust. Zenodo. [PAPER DOI]

The DTI framework the engine implements: Snyder, J. A. (2026). The Data Trust Index: A Multidimensional Framework for
Evaluating Health Data Integrity in AI Systems. Zenodo. https://doi.org/10.5281/zenodo.19601616

Data Trust Index is a trademark of SuperTruth Inc. DTI and BII score data records and software-agent behaviour; they
do not diagnose, treat, or make recommendations about any patient.
