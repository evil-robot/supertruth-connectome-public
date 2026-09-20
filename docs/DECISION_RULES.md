# Decision rules: connectome distillation whitepaper

v0.1, 2026-09-20. Each rule names the failure it prevents, the number that proves it, and the check that enforces
it. The checks live in `qa_adversary.py` (one test per rule), run after every pipeline cycle and before any
table is rendered. A rule with no check is marked **NO CHECK** so nobody claims it by accident. Floors live in
`baseline.json` and ratchet one way. Companion: `PROTOCOL.md`.

Two incidents bought the shape of this file: HSE 8/29 (a checker with no fixed point drifts with the data it
checks) and the 9/16 pack-removal incident (a file changed is not a system changed; verify the live table).
Rules below that cite "protocol" cite PROTOCOL.md sections.

## Rules

| # | Rule | Failure it prevents | Number that proves it | Check |
|---|---|---|---|---|
| 1 | Clean and corrupted forms of one base row, and all variants of one base patient, sit in the same split. | Near-duplicate leakage inflating every arm; the wiring claim becomes a memorization contest. | straddling groups = 0 | `qa_adversary.py::test_no_pair_straddle` builds the split, then for every `base_id` asserts one split label; ALSO plants one straddled pair in a copy and requires the test to go red (induced failure kept as `fixtures/straddle_red.json`). |
| 2 | All windows of one agent sit in one split. | Sliding windows share up to 290 events; a TEST window is a TRAIN window shifted by 10 events. | straddling agents = 0 | `test_no_agent_straddle`, same induced-red pattern. |
| 3 | No two records are identical once `id` is removed. | `random.Random(f"{key}-{i}")` is deterministic and the name pool is 24 x 24; extended generation can collide. | exact duplicates = 0; near duplicates (Jaccard over cells >= 0.95, different base) reported, not blocked | `test_no_duplicate_records` (sha256 of canonical serialization); `report_near_duplicates`. |
| 4 | Record id carries no corruption signal. | `corrupt()` uses fixed id ranges and `Record {id}` is in the engine's payload. | AUROC of id -> corrupted <= 0.55 on the full corpus | `test_id_not_predictive` fits a 1-feature logistic model on id; fails above 0.55. Induced red: a corpus cut with the original range rule. |
| 5 | The teacher is deterministic under the frozen clock. | Recency and consent age read `Date.now()`; two teacher batches on different days disagree and the student learns the date. | 3 repeated scorings of 500 records: 0 mismatches on any field; live spot-check 50/50 exact | `test_teacher_deterministic`; `test_live_matches_local` (runs only on the AS_OF UTC day; otherwise SKIPPED and printed as such, never PASSED). Induced red: unfreeze the clock in a copy and require a mismatch on at least one Recency value. |
| 6 | No target-derived column reaches the feature vector. | composite, tier, or a teacher dimension encoded by accident (e.g. a "flag" field the engine emits). | 0 features with |corr| > 0.999 to any target; 0 feature names in the engine's OUTPUT field list | `test_no_target_columns_in_features` checks names against `DTIResult` and `ScoredDimension` keys and checks correlations. |
| 7 | Every scaler and encoder is fit on TRAIN only. | Test moments leak through z-scoring. | scaler `fit` call count on non-TRAIN partitions = 0 | `test_scaler_fit_on_train_only` wraps the scaler and counts fits by partition tag. |
| 8 | A degenerate teacher dimension is excluded from MAE claims and named. | Constant targets make MAE trivially small and the composite claim hollow. | per-dimension SD on the corpus; excluded if < 2.0 points (DTI) or < 0.02 (BII signal) | `test_teacher_variance_gate` writes `degenerate_dims.json`; `render_table` refuses to print a per-dimension MAE for any listed dimension and prints "constant (<value>)" instead. Family 5 is always listed. |
| 9 | TEST is read once per (arm, seed). | Peeking; checkpoint selection on TEST. | evaluations per (arm, seed) = 1 unless `--reason` | `test_test_set_read_once` reads `eval_ledger.jsonl` (append-only, hash-chained) and fails on a second entry without a reason. |
| 10 | Null graphs match the real graph on what they are supposed to hold. | A "shuffle" that changed degrees or signs or lost edges makes the wiring comparison meaningless. | b: in-degree and out-degree vectors identical to a, sign per edge identical to a's presynaptic sign, E identical, `syn_count` multiset identical. c: N and E identical, `syn_count` multiset identical, 0 self-loops, 0 duplicate pairs | `test_null_graphs_match_degree_and_size`; induced red: a shuffle with one swap skipped. |
| 11 | The substrate is frozen during training. | An optimizer step that touches indices, signs, or membership masks turns arm a into arm d. | sha256 of (indptr, indices, edge_sign, sensory mask, readout mask) before and after every epoch equal | `test_graph_frozen` (hash at epoch 0 vs epoch end); `requires_grad` is False on those tensors. |
| 12 | Edge gains may never flip sign. | `exp(w)` keeps magnitude positive by construction; a code path that parameterizes gain directly could learn a sign flip and violate Dale's law. | count of edges where `sign * gain < 0` = 0 after training | `test_no_sign_flips`. |
| 13 | Readout is reachable within T. | If sensory-to-readout paths exceed T = 8 hops, the readout sees zeros and any learning is through bias alone. | share of readout neurons reachable from the sensory set within T hops, on graph a, printed; must be >= 0.90 or T is raised before the freeze | `test_readout_reachable_within_T` (sparse BFS, T steps). |
| 14 | Numbers reported for arm g come from the API's usage object and a dated price table, never from memory. | A $ per record figure typed from recollection. | every cost row cites `prices.json` with `retrieved_from: claude-api skill` and a date | `test_cost_rows_have_price_source`; the price file is created by the run, absent by default, and `render_table` refuses a cost row without it. |
| 15 | Every figure and table carries the complete provenance footer. | A figure claiming a period, a graph, or a corpus it does not cover. | 0 footers with a missing field (protocol section 13) | `test_footer_complete` parses every rendered footer against the field list. |
| 16 | The BII window encoding equals what the live pipeline would see. | The offline replica sees 50 of a type the live 300-event fetch would have trimmed. | 50 replayed windows: offline BII and 4 signals equal live sqlite `TestClient` results to 4 decimals | `test_window_cap_matches_live` (imports the VIGIL app in test mode; SKIPPED with a loud line if the repo is absent, never PASSED). |
| 17 | The BII teacher runs under the seed policy and empty registries. | A registry entry or policy version drifting into the replica. | policy digest = `5d8db364...8573859`; registry and blueprint inputs = None | `test_bii_seed_policy_pinned` compares the digest to `vigil/tests/test_policy.py`'s constant. |
| 18 | Output-range coverage gates pass before any split is cut. | Corpora that never reach a tier or a gate make the classifier metrics meaningless. | DTI Corpus B: each of 5 tiers >= 8%; BII Corpus C: each of 4 gates >= 10%, alignment signal < 1 in >= 15% | `test_output_coverage`. |
| 19 | Arm comparisons are paired and Holm-corrected within the primary family. | Cherry-picking one of many comparisons. | primary family = {a-b, a-c, a-e} per task; adjusted p printed beside raw | `test_primary_family_fixed` asserts the family list in `analysis.py` equals this table. |
| 20 | Seeds are >= 5 and identical across arms. | An arm with fewer seeds or different seeds is not comparable. | seed set {1..5} (or {1..10} if the pilot rule fires) present for a, b, c, d | `test_seed_sets_match`. |
| 21 | Determinism of the local arms is measured, not assumed. | MPS scatter kernels can be nondeterministic. | bitwise agreement share across 3 inferences on 300 records, printed per arm | `test_determinism_measured` requires the row to exist; it does not require 1.00. |
| 22 | The wiring sentence is one of three pre-written sentences. | Post-hoc wording that softens or inflates. | sentence in results == one of the three strings in `sentences.py` | `test_wiring_sentence_prewritten`. |
| 23 | Floors ratchet up only, with a reason. | Turning red green by lowering a bar. | `baseline.json` floors may only meet or exceed the prior file; changes need `--rebaseline --reason` | `test_ratchet_monotone`; lowering raises; rebaseline without a reason raises. |
| 24 | Spot truths match. | A lost aggregation slice or an encoding drift that leaves every average plausible. | frozen (record_id, teacher composite, tier) triples and (window_id, BII) pairs equal the live recompute | `test_spot_truths`. |
| 25 | Synthetic status is stamped on every row and every caption. | A reader takes a synthetic tier distribution for a population fact. | `data_class == "synthetic"` on 100% of rows; "SYNTHETIC" in 100% of captions | `test_synthetic_stamp`. |
| 26 | Refused claims do not appear in the manuscript. | Drafting drift. | 0 matches for the phrase list in `refused_claims.txt` (e.g. "better than", "clinical", "patients", "10.5M", "166,691", "smaller than Claude") outside the section that lists them | `test_manuscript_has_no_refused_claims` (grep over the .md with an allow-list for section 11). |
| 27 | The teacher's identity is pinned to a commit and the paper cites it. | The engine changes between the data cut and publication. | pipeline.ts sha256 at run time equals the value in `teacher_pin.json`; VIGIL detection module hashes likewise | `test_teacher_pinned`; a mismatch halts the run. |
| 28 | Sign convention is a documented assumption with a sensitivity row. | Glu/His inhibitory is a modeling choice, not a measurement. | the a-plus row exists in the results and the assumptions log names A3 and A4 | **NO CHECK** beyond `test_results_have_sensitivity_row` (presence only). Whether the convention is right is not testable here. |
| 29 | The synthetic corpora are not claimed to resemble real data. | Calibration language creep. | the "output-range coverage" table is present and the population disclaimer sentence is verbatim | **NO CHECK** on truthfulness; `test_disclaimer_present` checks presence only. |
| 30 | Compute feasibility decided before training, once. | Switching graphs mid-study to make a result appear. | `graph_choice.json` written by the feasibility gate with timestamp before the first `train.py` ledger entry | `test_graph_choice_precedes_training`. |

## Adversarial testing of the verifier itself (gate 11)

`qa_adversary.py --self-test` must go red on each planted failure before any run is trusted: a straddled pair
(rule 1), a straddled agent (2), a duplicate row (3), the original id-range corruption (4), an unfrozen clock (5),
a target column renamed to look like a feature (6), a scaler fit on VAL (7), a constant dimension with a printed
MAE (8), a second TEST read (9), a shuffle with one skipped swap (10), a gradient step on `edge_sign` (11), a
gain parameterized without exp (12), a footer missing `Coverage` (15), a cost row with no price file (14), a
lowered floor (23), a moved spot truth (24), a caption without SYNTHETIC (25), the string "10.5M" in the
manuscript body (26). The red fixtures stay in `fixtures/red/` as standing regression proof. A verifier that
passes its own red fixtures is broken and the run stops.

## baseline.json (ratcheted floors)

```json
{
  "version": 1,
  "rebaselined_at": null,
  "reason": null,
  "floors": {
    "corpus_b_records": 0,
    "corpus_b_test_records": 0,
    "corpus_c_windows": 0,
    "corpus_c_agents": 0,
    "graph_edges": 0,
    "graph_neurons": 0,
    "non_degenerate_dti_dims": 0,
    "seeds_per_arm": 5,
    "tier_classes_covered": 5,
    "gate_classes_covered": 4,
    "readout_reachable_share": 0.0,
    "live_spot_check_passed": 0
  },
  "spot_truths": {
    "dti": [],
    "bii": []
  }
}
```

- Every floor starts at 0 (or the protocol minimum) and is raised by the first real run through
  `qa_adversary.py --rebaseline --reason "<why>"`, which writes `rebaselined_at` and `reason` and commits the file.
- A floor may never be lowered by the tool; lowering is a hand edit in a reviewed commit with the reason in the
  message, and the paper's methods section lists every such edit.
- `graph_edges` and `graph_neurons` pin the substrate: a rebuilt graph with fewer edges fails until someone says why.
- `non_degenerate_dti_dims` starts 0 and is set by the variance gate; a later generator change that drops a
  dimension into the constant list is red.

## Spot truths

Frozen once from a run whose live spot-check passed (rule 5): 12 DTI records (one per Corpus A vertical, or
12 from Corpus B stratified by tier) as `(record_sha256, dims[8], composite, tier)`, and 8 BII windows
`(window_sha256, bii, signals[4], gate)`. They are recomputed by the offline teacher on every cycle and compared
exactly. A drift in the teacher, the encoding, or the serialization breaks them before any average moves.
Seeded with `qa_adversary.py --seed-spot-truths` and never edited by hand.

## Dataset-health checklist (runs BEFORE any score is reported; output attached to the results)

1. Row counts per corpus, per split, per teacher class. Teacher class histograms per split; KS distance
   TRAIN vs TEST per dimension, printed.
2. Exact duplicates = 0 (rule 3); near-duplicate count printed.
3. Pair straddle = 0 (rule 1); agent straddle = 0 (rule 2).
4. Id predictiveness AUROC <= 0.55 (rule 4).
5. Teacher determinism 3/3 (rule 5); live spot-check 50/50 or SKIPPED with the reason printed.
6. Degenerate dimension list (rule 8) and the non-degenerate count against its floor.
7. Feature-target correlations, top 10 printed; none above 0.999 (rule 6).
8. Max VIF over numeric features, printed (no threshold; informational).
9. Missingness per feature, printed.
10. Output-range coverage (rule 18).
11. Window-cap parity 50/50 (rule 16); policy digest pinned (rule 17).
12. Substrate hashes equal `data/README.md` sha256 values; graph hash equals `graph_choice.json`.
13. Seeds present and identical across arms (rule 20).
14. Feature spec hash, split hash, corpus hash, teacher pin: all present and equal to the footer values.

If any line fails, no metric is printed; the health report is the only output.

## Provenance footer (every figure, table, and results file)

```
Source: MaleCNS v1.0 (gs://flyem-male-cns/v1.0/...; sha256 in data/README.md; CC-BY 4.0; Berg et al. 2026)
 | Graph: N=<n> (superclass non-null), E=<e> (weight>=<thr>), sign policy <mod>/<unc>, graph sha256 <hash>
 | Teacher: <pipeline.ts commit | VIGIL commit + policy digest>, clock frozen at <AS_OF>
 | Data: <corpus> v<gen hash>, run_seed <s>, <train>/<val>/<test> records, split sha256 <hash>, SYNTHETIC, zero PHI
 | Coverage: TEST only, <n> records, seeds {..}; degenerate dims excluded: <list or none>
 | Feature spec <hash> | Evaluated <UTC> | LLM arm: <model id>, <params>, prices from claude-api skill retrieved <date>
```
Fields: source system, snapshot date (download date and teacher commit), coverage (which split, how many, which
seeds, which dimensions excluded), seed. Rule 15 enforces completeness. A figure may not claim a period, a graph,
or a corpus the data does not cover; where a field is unknown it prints `unknown`, never a guess.

## Running

```
uv run --project ~/Projects/ds-lab python qa_adversary.py                 # all rules, after every cycle
uv run --project ~/Projects/ds-lab python qa_adversary.py --self-test     # verifier must go red on fixtures/red/
uv run --project ~/Projects/ds-lab python qa_adversary.py --seed-spot-truths   # once, after a passing live check
uv run --project ~/Projects/ds-lab python qa_adversary.py --rebaseline --reason "..."
```
Interpreter pinned via the ds-lab project; never bare `python3` (9/14-16 incident). Torch runs in
`~/Projects/supertruth-connectome/.venv` (python3.12 pinned in requirements.txt); the adversary imports the
graph artifacts, not torch.
