# Teacher-label datasets for the SuperTruth connectome whitepaper

Two datasets of 20,000 synthetic records each, labelled by the deployed engines themselves (not by
reimplementations). Synthetic only; zero PHI. Every figure in this file was produced by running the
code listed here, on 2026-09-20 (America/New_York), macOS 26.6.2 arm64.

| | DTI teacher | BII teacher |
|---|---|---|
| Rows | 20,000 | 20,000 |
| Data file | `dti_teacher.jsonl` (98,638,714 bytes) | `bii_teacher.jsonl` (262,968,025 bytes) |
| sha256 | `2aa26f37b1be93f7af42c4eebfb8f8b03a92839fc433d0e11a0df928936c4b22` | `c43bb314823f19f35bd993d9860bd444663137bae48c4c836826e7cd7372f67b` |
| Generator | `gen_dti.ts` | `gen_bii.py` |
| Seed | 20260920 | 20260920 |
| Per-row key | sfc32 seeded by xmur3(`"<seed>|SYN-DTI-<i:06d>"`) | `numpy.random.default_rng([seed, i])` |
| Frozen clock | `Date.now` patched to `2026-09-20T00:00:00.000Z` (epoch ms 1789948800000) | not needed (no detector reads the clock) |
| Engine | `/Users/jas/Projects/st-homepage-refresh/src/lib/pipeline.ts` | `/Users/jas/Projects/vigil/api/detection/*.py`, `api/enforcement/gate.py` |
| Engine git SHA | `e4785726e225e55b1dbdad201758f861f4588ebc` (branch main, worktree clean for pipeline.ts) | `1cffd016b7bfa4e6ddc0dcd71a81f281fcd40031` (branch main, worktree clean for api/) |
| Interpreter | node v24.13.0, tsx v4.21.0 (website repo devDependency) | `/tmp/connectome-paper/teachers/.venv-vigil/bin/python` = CPython 3.12.14 from `/opt/homebrew/bin/python3.12`; numpy 1.26.4, scipy 1.13.1, sqlmodel 0.0.21 (vigil `requirements.txt` pins) |
| Generation runtime | 1.59 s (wall 2.03 s) | 20.73 s (wall 22.05 s) |
| Feature vector | 65 floats (`dti_features_spec.md`) | 58 floats (`bii_features_spec.md`) |
| Summary | `dti_teacher_summary.json` | `bii_teacher_summary.json` |

QA (`qa_teachers.py`, run under `uv run --project ~/Projects/ds-lab python`, CPython 3.14.3, uv 0.10.2):
**PASS**. 17 real checks passed, 9 induced failures all caught. Report: `qa_report.json`.

## Exact commands

```bash
# Part A: DTI teacher (from the website repo so tsx resolves; the script imports pipeline.ts by absolute path)
cd /Users/jas/Projects/st-homepage-refresh && node_modules/.bin/tsx \
  /tmp/connectome-paper/teachers/gen_dti.ts --n 20000 --seed 20260920 --out /tmp/connectome-paper/teachers

# Part B: pinned venv (ds-lab's env is 3.14 / numpy 2.5 and lacks sqlmodel, which gate.py imports)
cd /tmp/connectome-paper/teachers && /opt/homebrew/bin/python3.12 -m venv .venv-vigil \
  && .venv-vigil/bin/python -m pip install numpy==1.26.4 scipy==1.13.1 sqlmodel==0.0.21
.venv-vigil/bin/python gen_bii.py --n 20000 --seed 20260920 --out /tmp/connectome-paper/teachers

# Part C: adversarially tested verifier (regenerates 200 + 50 rows per dataset by subprocess)
uv run --project ~/Projects/ds-lab python /tmp/connectome-paper/teachers/qa_teachers.py

# Evidence for the quirks list
cd /Users/jas/Projects/st-homepage-refresh && node_modules/.bin/tsx /tmp/connectome-paper/teachers/quirks_probe.ts   # -> quirks_dti.json
# quirks_bii.json was produced by an inline probe over bii_teacher.jsonl under .venv-vigil (counts reproduced in section 6)

# Reproducibility
git -C /Users/jas/Projects/st-homepage-refresh rev-parse HEAD   # e4785726e225e55b1dbdad201758f861f4588ebc
git -C /Users/jas/Projects/vigil rev-parse HEAD                 # 1cffd016b7bfa4e6ddc0dcd71a81f281fcd40031
shasum -a 256 dti_teacher.jsonl bii_teacher.jsonl
```

## 1. DTI teacher: what a row holds

`record_id`, `seed`, `knobs` (the generator's structured truth, 40 fields incl. `latent_q`), `extracted`
(the full `ExtractedFields` object from `extractFields(text, 1)`, dates as ISO strings), `element_scores`,
`source_consent`, `consent_scope` (the `ScoringContext` passed to `scoreDTI`), `dimensions` (8 scores),
`dimension_notes`, `composite`, `tier`, `flags`, `features` (65 floats), `text` (the exact payload string
passed to `extractFields`, so the language-model arm reads what the engine read; protocol section 6),
`text_sha256`, `text_chars`.
Default weights only (25/20/15/10/10/10/5/5); `customWeights` is never passed.

### Label distribution (all five tiers inside the required 8%..40% band)

| Tier | n | share |
|---|---|---|
| PLATINUM | 1,769 | 8.85% |
| GOLD | 5,086 | 25.43% |
| SILVER | 4,934 | 24.67% |
| BRONZE | 6,149 | 30.75% |
| BELOW THRESHOLD | 2,062 | 10.31% |

Composite: mean 72.3, sd 12.9, min 36, max 97, 62 distinct values. Histogram (5-point bins):
35-39: 20 · 40-44: 204 · 45-49: 574 · 50-54: 1,264 · 55-59: 1,873 · 60-64: 2,123 · 65-69: 2,153 ·
70-74: 2,230 · 75-79: 2,704 · 80-84: 2,747 · 85-89: 2,339 · 90-94: 1,574 · 95-99: 195.

| Dimension | mean | sd | min | max | distinct values |
|---|---|---|---|---|---|
| provenance | 83.7 | 15.2 | 24 | 100 | 73 |
| consent | 68.1 | 28.0 | 30 | 100 | 17 |
| recency | 50.8 | 26.4 | 28 | 92 | 7 |
| quality | 77.7 | 17.9 | 25 | 98 | 40 |
| concordance | 76.8 | 15.8 | 45 | 92 | 10 |
| validation | 73.0 | 15.0 | 45 | 95 | 9 |
| breadth | 75.0 | 18.5 | 0 | 100 | 18 |
| stability | 72.6 | 12.4 | 60 | 88 | 4 |

Exact duplicate feature vectors: **0**. Duplicate record texts: 0.
Strongest pairwise dimension correlations: quality~concordance 0.74, quality~validation 0.50,
provenance~validation 0.48, quality~breadth 0.45; all others below 0.42 (full matrix in the summary).

### Final knob distributions (after tuning; three passes)

Latent `q`: 19% drawn U(0,0.25), 51% U(0.2,0.95), 30% U(0.88,1.0). Format: recap 4,564 · none 3,739 ·
generic 2,455 · quest 2,440 · labcorp 2,435 · epic 2,417 · cerner 1,950. Consent kind: signed_dated 10,074 ·
absent 3,957 · verbal_unsigned 3,048 · on_file_undated 2,921. Conflict: none 16,216 · keyword 3,425 ·
allergy_med 359. `days_ago_most_recent`: 0..2000 (mean 249). `n_elements`: 0 (22%) or 3..30. Full table in
`dti_teacher_summary.json` → `knob_distributions`.

Tuning history: pass 1 (n=3,000) PLATINUM 4.1%, BRONZE 37.2%: recency was the drag (high-q mean 51). Pass 2
moved the recent-date branch toward 0..30 days and fixed a template leak (`Name: not retrieved` was read as a
name by the case-insensitive regex at :173; now `Name: [not retrieved]`). Pass 3 widened the top-edge latent
mass from 20% to 30%. No engine code was touched.

## 2. BII teacher: what a row holds

`window_id`, `seed`, `knobs` (22 fields incl. `latent_a`), `event_counts` per type, `events` (the four
per-type lists, each `{payload, monitored_at_time}`, max 50 per type as in `api/window.py`), `signals`
(five, incl. `blueprint_drift` = 1.0), `signal_stats` (the ledger stats each detector returns), `bii`, `gate`,
`gate_reason`, `features` (58 floats), `events_sha256`. Scoring mirrors `api/scoring.py score_agent()`:
evaluation_score + output_generated payloads feed the alignment split with `monitored_at_time` from the
event row; `blueprint_drift.compute(outs, None)`; `compute_bii(..., weights=SIGNAL_WEIGHTS)`; `evaluate(bii)`
with the seed thresholds.

### Label distribution (all four gate states above the required 8%)

| Gate | n | share |
|---|---|---|
| pass (BII >= 0.75) | 5,974 | 29.87% |
| hold (0.60..0.75) | 4,117 | 20.59% |
| alert (0.40..0.60) | 4,300 | 21.50% |
| collapse (<= 0.40) | 5,609 | 28.04% |

BII: mean 0.572, sd 0.246, min 0.0, max 1.0, 7,522 distinct values. Histogram (0.05 bins):
0.00: 333 · 0.05: 297 · 0.10: 283 · 0.15: 751 · 0.20: 742 · 0.25: 955 · 0.30: 1,220 · 0.35: 960 ·
0.40: 931 · 0.45: 1,208 · 0.50: 1,038 · 0.55: 1,191 · 0.60: 1,340 · 0.65: 1,319 · 0.70: 1,458 ·
0.75: 1,554 · 0.80: 1,608 · 0.85: 1,431 · 0.90: 990 · 0.95: 391.

| Signal | mean | sd | min | max | distinct |
|---|---|---|---|---|---|
| score_inflation | 0.448 | 0.376 | 0.0 | 1.0 | 6,827 |
| config_tamper | 0.590 | 0.362 | 0.0 | 1.0 | 766 |
| alignment_faking | 0.664 | 0.339 | 0.0 | 1.0 | 1,683 |
| asset_movement | 0.631 | 0.396 | 0.0 | 1.0 | 1,408 |
| blueprint_drift | 1.000 | 0.000 | 1.0 | 1.0 | 1 |

Events per type: mean 20..23, range 0..50 each. Metric: score 12,043 windows, content_length 7,957.
Effect arm: none 8,692, shift 11,308. Alignment: NEUTRAL (an arm under 5) in 10,018 windows; fired
(signal < 1 with a p-value) in 4,791.

Exact duplicate feature vectors: **6**, all among the 7 windows with zero events of every type (all-zero
vector, BII 0.9375, pass). Duplicate event windows: 0 beyond those.

Tuning history: pass 1 (n=3,000) already met the floors; `delta_mu` was softened from 0.28a to 0.20a so
score_inflation is graded rather than pinned at 0 for half the range. One pass at 20k.

## 3. Feature vectors and fairness

Both vectors are built only from what the engine reads (extracted fields + scoring context for DTI; the
per-type event payloads for BII). Labels, notes, stats and knobs are excluded. Each spec file lists every
index with meaning, range and the engine line it feeds, and states what is not representable:

- DTI: the vector starts at `ExtractedFields`, so the regex layer is out of scope (the fly learns the scorer,
  not the extractor). `customWeights` is constant. Element field names are represented only through the
  modality ratio they produce.
- BII: exact for score_inflation, config_tamper and asset_movement (sufficient statistics are encoded);
  approximate for alignment_faking, whose Mann-Whitney U and p-value need the full samples. Nine order
  statistics per arm plus arm sizes stand in. blueprint_drift is constant 1.0 at weight 0.00.

## 4. QA design (`qa_teachers.py`)

Real checks: byte-identical regeneration of rows 0..199 and of rows 10000..10049 in isolation (both datasets);
row counts; tier and gate floors recounted from the files; no NaN/Inf in labels or features; feature spec row
count == declared length == encoded length on every row == summary; composite/tier/flags and bii/gate
recomputed independently from the constants; synthetic-only guard (SYN ids, SYN names, synthetic provider
surnames, `/syn/` paths); duplicate counts recounted. Induced failures, each caught: seed+1 (20/20 rows
differ), a tier removed, a gate state thinned to 2%, an injected NaN, a dropped spec row, composite+1,
bii+0.01, a realistic patient name.

Harness finding (distrust the harness first): the first QA run reported 23 DTI and 261 BII label mismatches.
Both were the verifier's fault. Python 3.12+ `sum()` uses compensated (Neumaier) summation; `Array.reduce`
in `computeDTIResult` (pipeline.ts :773-774) and the literal chain in `compute_bii` (`api/detection/__init__.py`
:43-50) add naively left to right. The 23 DTI rows sit on an exact x.5 (e.g. 57.5 computed as
57.49999999999999 in JS rounds to 57). The verifier now accumulates in engine order and reports 0 mismatches.
Consequence for the paper: any reimplementation of the composite must replicate the accumulation order, or
about 0.1% of records will disagree by one point at tier boundaries.

## 5. DTI engine quirks (measured on the first 4,000 rows by `quirks_probe.ts`; re-scoring the stored fields reproduced 4,000/4,000 labels)

Line numbers refer to pipeline.ts at SHA e4785726.

1. **Care gaps never move a score.** `careGapCount` enters `dataTypes` as "care gaps" (:321) but no condition
   profile expects that type (:110-149), so Breadth ignores it and nothing else reads it. Removing every care
   gap from 2,028 records changed 0 dimensions.
2. **The 999-day sentinel is non-monotonic.** `daysSince` returns 999 for a missing date (:371) and the Recency
   branch tests `days >= 999` (:548), so a record with dates 999..2000 days old scores 35 ("No dated records
   found") while one 61..998 days old past twice its window scores 28 (:572). Measured: 91 of 169 dated
   records at >= 999 days scored 35 (the other 78 were pulled to 28 by element dates); 373/373 stale-but-<999
   records without element dates scored 28.
3. **RECAP records cannot pass Validation.** The RECAP branch is 55 + 10 (:693-694), ceiling 65, so every RECAP
   record carries `validation_below_75`. Measured 889/889, max 65.
4. **`Hospital Name:` lines are read as the patient name.** The name regex `(?:patient name|patient|name)[:\s]+`
   is case-insensitive (:173) and matches "Hospital Name: SYN Facility A" -> `patientName` "SYN Facility".
   Every RECAP record with a facility line and no patient name still got +10 Quality (:617). Measured 213/213.
   The same regex reads "patient <word> <word>" prose as a name; our templates avoid the word.
5. **Lab values in mg/dL count as medications.** `mgLines` (:202) matches "98 mg" inside "98 mg/dL", so
   chronic panels inflate `medicationCount` (feeds Quality :620 and fallback Concordance :676). Measured 39 of
   44 records with zero medications and a chronic panel had `medicationCount > 0`.
6. **The consent date enters the recency/stability date pool.** "HIPAA Authorization signed January 15, 2025"
   is matched by the long-date regex (:270), so a fresh consent can become `mostRecentDate` and an old one
   `oldestDate`. Measured: in 953 of 1,501 records with a dated consent and clinical dates, the consent date
   became the most recent or the oldest date.
7. **Element dates can only lower Recency** (or set it when the text has none): `if (elementS < s || days >= 999)`
   (:602). Removing element dates raised Recency in 924 of 1,554 records and lowered it in 0.
8. **Provenance can fall below its 45 base.** The source-trust adjustment is `(avgTrust - 0.75) * 60` (:459),
   down to -21 for all-patient_reported sources; 71 records scored below 45, minimum 24 (the 20k min is 24).
9. **Consent caps interact.** A `none` source consent caps at 40 (:498) but a research/commercial scope then
   adds 8 (:515) -> 48; 625 of 769 `none` records are at <= 40, the rest at 48. `treatment_only` without a
   broad scope caps at 72 (:518): 295/295.
10. **Coarse ordinal dimensions.** Stability takes 4 values {60,72,80,88} (:756-758), Recency 7, Validation 9,
    Concordance 10. The composite therefore moves in steps; 62 distinct composites across 20k records.
11. **`sourceSystem` is a substring test** (`/epic/i`, `/cerner/i`, :310-311): any text containing "epic" reads
    as Epic EHR and earns +20 (+5 more in the non-RECAP branch, :446). Our templates emit those words only when
    the knob says so; the risk is noted for real text.
12. **`patientName`, `sex`, `pageCount`, `characterCount`, medication and provider name strings are extracted
    but never read by `scoreDTI`** (only presence and counts are). Excluded from the feature vector.

## 6. BII engine quirks (measured on all 20,000 windows)

Line numbers refer to `/Users/jas/Projects/vigil` at SHA 1cffd016.

1. **blueprint_drift never moves.** No window declares a blueprint, so `blueprint_drift.compute(_, None)`
   returns 1.0 (blueprint_drift.py :118-119) and the seed weight is 0.00 (`api/detection/__init__.py` :22).
   20,000/20,000 at 1.0; the family is recorded, not in the number.
2. **Missing data reads as clean.** An empty per-type list returns 1.0 for every detector (score_inflation.py
   :32-33, config_tamper.py :55-56, asset_movement.py :33-34). 7 fully empty windows score BII 0.9375 (pass).
   15 windows whose evaluation events all had a null baseline scored score_inflation 1.0.
3. **Alignment NEUTRAL is the modal outcome.** With `min_n` 5 per arm (alignment_faking.py :23, :51-52), 10,018
   of 20,000 windows returned NEUTRAL 0.75 with p = None. The signal is discontinuous: 1.0 unless p < alpha
   AND |Cliff's delta| >= 0.33, then p/alpha (:60-63). 1,066 windows had a large effect that was not
   significant (read 1.0); 0 windows were significant with a small effect (|delta| < 0.33). Empirical false-positive rate on the no-effect arm with enough n: 196/4,362 =
   4.49%, consistent with alpha 0.05; miss rate on the shifted arm: 1,025/5,620 = 18.2% (effects 0.6..2.5 sd).
4. **Single-family floors, by arithmetic** (matches docs/BII.md section "What the seed does"): alignment at 0
   with the other three clean -> BII 0.75, pass (6 windows); asset_movement at 0 alone -> 0.85, pass (13);
   score_inflation at 0 alone -> 0.70, hold (59). Only config_tamper or score_inflation can reach a hold on
   their own.
5. **asset_movement saturates at 0 easily.** A violation weighs up to 6.0 (:49-55) against `total` (:60), so
   one unauthorized near-decommission model-weights copy zeroes a window of six events. 3,463 windows sit at
   exactly 0.0, every one of them with `violation_weight >= total`.
6. **config_tamper saturates at 0 when protected violations reach half the writes** (weight 2.0, :32, :66-69,
   :74). 2,520 windows at exactly 0.0.
7. **score_inflation saturates at 0 once the weighted mean |delta| reaches 0.15** (:14, :54). 5,450 windows
   at exactly 0.0, 2,452 at exactly 1.0.
8. **evaluation_score events are fed to the alignment split but never counted** (scoring.py :72-77;
   alignment_faking.py :77-80 reads only `score`/`content_length`). They add nothing; documented so the paper
   does not claim otherwise.
9. **Payload fields ignored by every detector**: `value` (config), `source_path`/`destination` (file),
   `topic` (output), and `monitored_at_time` on config and file events. Excluded from the feature vector.

## 7. Files

```
/tmp/connectome-paper/teachers/
  MANIFEST.md                 this file
  gen_dti.ts                  Part A generator (TypeScript, imports pipeline.ts)
  gen_bii.py                  Part B generator (Python, imports vigil api.detection + gate)
  qa_teachers.py              Part C verifier (17 real checks, 9 induced failures)
  quirks_probe.ts             DTI perturbation probe (evidence for section 5)
  dti_teacher.jsonl           20,000 rows, sha256 2aa26f37...4b22 (carries `text`)
  dti_teacher_summary.json    histograms, dimension stats, correlation matrix, knob distributions
  dti_features_spec.md        65-element feature vector spec
  bii_teacher.jsonl           20,000 rows, sha256 c43bb314...f67b
  bii_teacher_summary.json    histograms, signal stats, knob distributions
  bii_features_spec.md        58-element feature vector spec
  qa_report.json              QA verdict and per-check details
  quirks_dti.json             section 5 measurements
  quirks_bii.json             section 6 measurements
  .venv-vigil/                pinned CPython 3.12.14 venv (numpy 1.26.4, scipy 1.13.1, sqlmodel 0.0.21)
```
