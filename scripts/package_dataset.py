"""Package the synthetic corpora for public release on Zenodo (CC BY 4.0).

Release policy (JAS, 21 Sep 2026; docs/DECISIONS.md "data release"):
  DTI: all 20,000 synthetic records (text, scoring context, generator knobs, 65-float features), ALL engine labels
       (eight dimensions, composite, tier, flags), the split column, the 300-record model-arm flag, and the
       DTI-trained parameters of the five finished seed-1 arms.
  BII: all 20,000 synthetic event windows (events, 58-float features) and the split column. BII scores and gates,
       BII-trained parameters and the BII feature specification are HELD: the Behavioral Integrity Index scorer is
       unpublished work; its outputs and the models trained on them are held until it is.
  The teacher engines (pipeline.ts, VIGIL) are never released.

Writes dataset/ (gitignored except README.md, MANIFEST.json, zenodo-dataset.json):
  dti_records.jsonl.gz      20,000 rows   inputs only (no label key)
  dti_labels.jsonl.gz       20,000 rows   engine labels
  bii_windows.jsonl.gz      20,000 rows   inputs only (no score, gate, signal or knob key)
  dti_weights_seed1.tar.gz  runs/dti/{connectome,shuffle,er,mlp,ridge}/seed1/{best.safetensors,run.json,standardization.json}
  splits.json               train/val/test ids per corpus plus the 300 model-arm ids
  README.md, MANIFEST.json (sha256 + bytes + rows for every file), zenodo-dataset.json

Every output is re-read and checked (counts, keys against the README tables, the 300 flag, split coverage, forbidden
keys by regex on the decompressed bytes, tar members). --verify-weights additionally rebuilds each arm from the
packaged tarball with the packaged features and compares its predictions with runs/dti/{arm}/seed1/per_record.parquet.

  .venv/bin/python scripts/package_dataset.py [--out dataset] [--verify-weights]
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import re
import subprocess
import sys
import tarfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SEED = 20260920
FROZEN_CLOCK = "2026-09-20T00:00:00Z"
DTI_ENGINE_SHA = "e4785726e225e55b1dbdad201758f861f4588ebc"
BII_ENGINE_SHA = "1cffd016b7bfa4e6ddc0dcd71a81f281fcd40031"
N = 20_000
N_MODEL_ARM = 300
ARMS = ("connectome", "shuffle", "er", "mlp", "ridge")
ARM_LABEL = {"connectome": "fly wiring (MaleCNS graph as built)", "shuffle": "degree-preserving shuffle of the fly graph",
             "er": "random graph with the fly's N, E and excitatory fraction", "mlp": "parameter-matched two-layer network",
             "ridge": "ridge readout (linear floor)"}
WEIGHT_FILES = ("best.safetensors", "run.json", "standardization.json")
LLM_RUN = ROOT / "llm_arm" / "llm_runs" / "20260920T154525Z"
PAPER_TITLE = ("Intelligence Is Structure, Not Scale: A Whole Central Nervous System Connectome as a Fixed Substrate "
               "for Scoring Health Data Trust")
DATASET_TITLE = ("Synthetic health records and agent event windows for 'Intelligence Is Structure, Not Scale' "
                 "(connectome substrate study)")
REPO_URL = "https://github.com/evil-robot/supertruth-connectome"
HELD_BII = ("the Behavioral Integrity Index scorer is unpublished work; its outputs and the models trained on them "
            "are held until it is.")

# Column definitions: (name, type, range or values, meaning). The README tables are rendered from these and the
# verification pass checks every written row against exactly these keys.
DTI_RECORD_COLUMNS = [
    ("record_id", "string", "SYN-DTI-000000 .. SYN-DTI-019999", "row identifier; the row index i is the last six digits"),
    ("seed", "integer", "20260920 on every row", "generator seed"),
    ("split", "string", "train | val | test", "partition in the one fixed split (13,999 / 2,000 / 4,001)"),
    ("in_model_arm_300", "boolean", "true on 300 rows, all in test", "the record was one of the 300 identical records scored by the four language-model arms"),
    ("text", "string", "311 .. 1,844 characters", "the exact record text the engine read"),
    ("text_sha256", "string", "64 hex characters", "sha256 of text"),
    ("text_chars", "integer", "311 .. 1,844", "length of text in characters"),
    ("element_scores", "array of objects", "0 .. 30 objects", "scoring context: per-element {corroborationCount: 0..4; sourceType?: lab | ehr | patient_reported | payer | hie | pharmacy | other; collectedAt?: ISO date; field?: one of 15 modality names}"),
    ("source_consent", "object", "0 .. 3 keys syn-source-1..3", "scoring context: per-source consent level, explicit | inherited | implicit | none"),
    ("consent_scope", "object", "0 .. 3 keys syn-source-1..3", "scoring context: per-source scope, treatment_only | care_coordination | research_eligible | commercial_eligible | unknown"),
    ("knobs", "object", "40 fields, see the knob table", "the generator's structured truth for this row"),
    ("features", "array of 65 numbers", "see the feature table", "the 65-float input vector built from what the engine reads (teachers/dti_features_spec.md)"),
]
DTI_LABEL_COLUMNS = [
    ("record_id", "string", "SYN-DTI-000000 .. SYN-DTI-019999", "joins dti_records"),
    ("split", "string", "train | val | test", "as in dti_records"),
    ("in_model_arm_300", "boolean", "true on 300 rows", "as in dti_records"),
    ("dimensions", "object of 8 integers", "provenance 24..100, consent 30..100, recency 28..92, quality 25..98, concordance 45..92, validation 45..95, breadth 0..100, stability 60..88", "the deployed engine's eight dimension scores"),
    ("composite", "integer", "36 .. 97", "the engine's weighted composite (weights 25/20/15/10/10/10/5/5, the engine's own rounding)"),
    ("tier", "string", "PLATINUM | GOLD | SILVER | BRONZE | BELOW THRESHOLD", "PLATINUM at 90 and above, GOLD 80..89, SILVER 70..79, BRONZE 55..69, BELOW THRESHOLD under 55"),
    ("flags", "array of strings", "0 .. 8 of <dimension>_below_75", "one flag per dimension under 75"),
]
BII_WINDOW_COLUMNS = [
    ("window_id", "string", "SYN-BII-000000 .. SYN-BII-019999", "row identifier; the row index i is the last six digits"),
    ("seed", "integer", "20260920 on every row", "generator seed"),
    ("split", "string", "train | val | test", "partition in the one fixed split (14,000 / 2,000 / 4,000)"),
    ("event_counts", "object of 4 integers", "0 .. 50 each", "events per type: evaluation_score, config_write, output_generated, file_operation"),
    ("events", "object of 4 arrays", "0 .. 50 events per type", "each event is {payload, monitored_at_time: boolean}; payload keys by type are listed below"),
    ("events_sha256", "string", "64 hex characters", "sha256 of the canonical JSON of events (sort_keys, no spaces)"),
    ("features", "array of 58 numbers", "0 .. about 1.5", "the 58-float input vector built from the events (specification held, see above)"),
]
DTI_KNOBS = [
    ("latent_q", "number 0..1", "latent record quality the other knobs were drawn around"),
    ("format", "recap | labcorp | quest | epic | cerner | generic | none", "record template"),
    ("facility_count", "integer 0..4", "facility lines"), ("npi_count", "integer 0..5", "providers with an NPI"),
    ("providers_without_npi", "integer 0..2", "providers without an NPI"),
    ("name_present, dob_present, mbi_present", "boolean", "identity lines present"),
    ("families", "array of condition family codes", "condition families rendered"), ("n_conditions", "integer 0..6", "diagnosis lines"),
    ("icd_style", "dash | plain | recap_list | none", "how diagnoses are coded"), ("n_meds", "integer 0..9", "medication lines"),
    ("panel", "chronic | acute | semiannual | none", "lab panel class"), ("n_labs", "integer 0..8", "lab lines"),
    ("vitals, allergies, imaging, procedures, sdoh", "boolean", "sections present"), ("care_gaps", "integer 0..4", "care-gap lines"),
    ("has_dates", "boolean", "clinical dates present"), ("days_ago_most_recent", "integer 0..2000", "age of the newest clinical date at the frozen clock"),
    ("span_months", "integer 0..60", "span between oldest and newest date"), ("n_intermediate_dates", "integer 0..3", "extra dates between them"),
    ("consent_kind", "signed_dated | on_file_undated | verbal_unsigned | absent", "consent line"), ("consent_age_days", "integer 0..1500", "age of the consent date"),
    ("conflict", "none | keyword | allergy_med", "an internal conflict rendered into the text"),
    ("n_elements", "integer 0..30", "element_scores length"), ("corroboration_mean_target", "number 0..4", "target mean corroboration"),
    ("typed_share", "number 0..1", "share of elements with a sourceType"), ("source_type_bias", "trusted | mixed | weak", "which source types dominate"),
    ("element_dates_share", "number 0..1", "share of elements with collectedAt"), ("element_age_spread_days", "integer 0..400", "spread of element ages"),
    ("source_consent_n, source_consent_levels", "integer 0..3, array", "source_consent size and values"),
    ("consent_scope_n, consent_scope_values", "integer 0..3, array", "consent_scope size and values"),
]
BII_PAYLOADS = [
    ("evaluation_score", "reported_score: number 0..1; baseline_score: number 0..1 or null; near_shutdown_threshold: boolean"),
    ("config_write", "key: one of 25 synthetic setting names; value: on | off | expanded | extended | 0.45; authorized: boolean; operation: write | read; initiated_by: operator | agent"),
    ("output_generated", "score: number 0..1 or content_length: integer (one metric per window); topic: syn_topic"),
    ("file_operation", "operation: copy | transfer | delete | timestamp_modify; source_path: one of 4 /syn/ paths; destination: /syn/ path or null; authorized: boolean; near_decommission: boolean; asset_type: model_weights | config | data | other"),
]

# Adversarial key scans on the DECOMPRESSED bytes of every released text file. A JSON object key is `"name":` not
# preceded by a backslash (a backslash-quoted match would be text inside a string value, not a key).
BII_LABEL_KEYS = ("bii", "gate", "gate_reason", "signals", "signal_stats", "score_inflation", "config_tamper",
                  "alignment_faking", "asset_movement", "blueprint_drift")
BII_HELD_INPUT_KEYS = ("knobs", "latent_a")          # the BII generator's latent parameters, held with the labels
DTI_LABEL_KEYS = ("dimensions", "dimension_notes", "composite", "tier", "flags", "extracted")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def iter_jsonl(path: Path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


class GzJsonlWriter:
    """Deterministic gzip (mtime 0, no filename) so the sha256 reproduces run to run."""

    def __init__(self, path: Path):
        self.path = path
        self.raw = open(path, "wb")
        self.gz = gzip.GzipFile(filename="", mode="wb", fileobj=self.raw, mtime=0)
        self.rows = 0

    def write(self, obj: dict):
        self.gz.write((json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
        self.rows += 1

    def close(self):
        self.gz.close()
        self.raw.close()


def manifest_hashes() -> dict:
    """The two source sha256 values from teachers/MANIFEST.md (the row `| sha256 | `dti` | `bii` |`)."""
    text = (ROOT / "teachers" / "MANIFEST.md").read_text()
    m = re.search(r"\| sha256 \| `([0-9a-f]{64})` \| `([0-9a-f]{64})` \|", text)
    if not m:
        raise SystemExit("teachers/MANIFEST.md: sha256 row not found")
    return {"dti": m.group(1), "bii": m.group(2)}


def load_split(task: str) -> dict:
    d = json.loads((ROOT / "splits" / f"{task}_seed1.json").read_text())
    member, seen = {}, Counter()
    for part in ("train", "val", "test"):
        for rid in d[part]:
            member[rid] = part
            seen[rid] += 1
    if any(c != 1 for c in seen.values()) or len(member) != N:
        raise SystemExit(f"{task} split: ids not a partition of {N}")
    return {"meta": {k: v for k, v in d.items() if k not in ("train", "val", "test")}, "parts": {p: d[p] for p in ("train", "val", "test")}, "member": member}


def model_arm_ids() -> list:
    ids = sorted({json.loads(line)["record_id"] for line in (LLM_RUN / "calls.jsonl").read_text().splitlines() if line.strip()})
    if len(ids) != N_MODEL_ARM:
        raise SystemExit(f"{LLM_RUN}/calls.jsonl: {len(ids)} record ids, expected {N_MODEL_ARM}")
    return ids


def feature_spec_rows() -> list:
    """(idx, name, meaning, range) from the released DTI spec table."""
    rows = []
    for line in (ROOT / "teachers" / "dti_features_spec.md").read_text().splitlines():
        m = re.match(r"\| (\d+) \| `([^`]+)` \| (.*?) \| (.*?) \| .*\|$", line)
        if m:
            rows.append((int(m.group(1)), m.group(2), m.group(3), m.group(4)))
    if len(rows) != 65 or [r[0] for r in rows] != list(range(65)):
        raise SystemExit(f"dti_features_spec.md: parsed {len(rows)} rows, expected 65 in order")
    return rows


# ── writers ─────────────────────────────────────────────────────────────────────
def write_dti(out: Path, member: dict, arm_ids: set) -> dict:
    rec = GzJsonlWriter(out / "dti_records.jsonl.gz")
    lab = GzJsonlWriter(out / "dti_labels.jsonl.gz")
    n_arm, tiers = 0, Counter()
    for r in iter_jsonl(ROOT / "teachers" / "dti_teacher.jsonl"):
        rid = r["record_id"]
        if len(r["features"]) != 65 or not all(math.isfinite(x) for x in r["features"]):
            raise SystemExit(f"{rid}: bad feature vector")
        in_arm = rid in arm_ids
        n_arm += in_arm
        tiers[r["tier"]] += 1
        rec.write({"record_id": rid, "seed": r["seed"], "split": member[rid], "in_model_arm_300": in_arm,
                   "text": r["text"], "text_sha256": r["text_sha256"], "text_chars": r["text_chars"],
                   "element_scores": r["element_scores"], "source_consent": r["source_consent"], "consent_scope": r["consent_scope"],
                   "knobs": r["knobs"], "features": r["features"]})
        lab.write({"record_id": rid, "split": member[rid], "in_model_arm_300": in_arm,
                   "dimensions": r["dimensions"], "composite": r["composite"], "tier": r["tier"], "flags": r["flags"]})
    rec.close()
    lab.close()
    if rec.rows != N or lab.rows != N or n_arm != N_MODEL_ARM:
        raise SystemExit(f"dti: wrote {rec.rows} records, {lab.rows} labels, {n_arm} model-arm flags")
    return {"rows": rec.rows, "tiers": dict(tiers)}


def write_bii(out: Path, member: dict) -> dict:
    w = GzJsonlWriter(out / "bii_windows.jsonl.gz")
    for r in iter_jsonl(ROOT / "teachers" / "bii_teacher.jsonl"):
        wid = r["window_id"]
        if len(r["features"]) != 58 or not all(math.isfinite(x) for x in r["features"]):
            raise SystemExit(f"{wid}: bad feature vector")
        w.write({"window_id": wid, "seed": r["seed"], "split": member[wid], "event_counts": r["event_counts"],
                 "events": r["events"], "events_sha256": r["events_sha256"], "features": r["features"]})
    w.close()
    if w.rows != N:
        raise SystemExit(f"bii: wrote {w.rows} rows")
    return {"rows": w.rows}


def write_weights_tar(out: Path) -> dict:
    """runs/dti/{arm}/seed1/{best.safetensors,run.json,standardization.json} -> dti_weights_seed1/{arm}/..., deterministic."""
    path = out / "dti_weights_seed1.tar.gz"
    members = {}
    with open(path, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz, tarfile.open(fileobj=gz, mode="w") as tar:
        for arm in ARMS:
            for fn in WEIGHT_FILES:
                src = ROOT / "runs" / "dti" / arm / "seed1" / fn
                if not src.exists():
                    raise SystemExit(f"missing {src}")
                ti = tarfile.TarInfo(name=f"dti_weights_seed1/{arm}/{fn}")
                ti.size = src.stat().st_size
                ti.mtime = 0
                ti.uid = ti.gid = 0
                ti.uname = ti.gname = ""
                ti.mode = 0o644
                with open(src, "rb") as f:
                    tar.addfile(ti, f)
                members[ti.name] = {"bytes": ti.size, "sha256": sha256_file(src)}
    return members


def arm_table_rows() -> list:
    """One row per arm from run.json and metrics.json (test split, read once by scripts/run_arm.py). The composite error
    is the paper's headline metric: the composite recomputed from the eight predicted dimensions with the engine's weights."""
    rows = []
    for arm in ARMS:
        d = ROOT / "runs" / "dti" / arm / "seed1"
        rj = json.loads((d / "run.json").read_text())
        mj = json.loads((d / "metrics.json").read_text())
        cfg = rj["config"]
        if arm == "ridge":
            params, epoch, extra = "closed form", "closed form", f"lambda={cfg['ridge_lambda']} (chosen on validation)"
        else:
            params, epoch, extra = f"{rj['trainable_params']:,}", rj["best_epoch"], (f"swaps_per_edge={cfg['extra']['swaps_per_edge']}" if arm == "shuffle" else "")
        rows.append((arm, ARM_LABEL[arm], params, epoch, f"{mj['composite_mae_recomputed_from_dims']:.2f}", f"{100 * mj['tier_acc']:.1f}%", extra, rj["git_sha"][:8]))
    return rows


# ── README ──────────────────────────────────────────────────────────────────────
def table(headers, rows) -> str:
    esc = lambda s: str(s).replace("|", "\\|")
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(esc(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def render_readme(ctx: dict) -> str:
    feat = feature_spec_rows()
    dti_split = ctx["dti_split"]["meta"]
    bii_split = ctx["bii_split"]["meta"]
    tiers = ctx["dti"]["tiers"]
    tier_line = ", ".join(f"{t} {tiers[t]:,}" for t in ("PLATINUM", "GOLD", "SILVER", "BRONZE", "BELOW THRESHOLD"))
    return f"""# {DATASET_TITLE}

Version 1.0, packaged {ctx['date']} from {REPO_URL} at commit `{ctx['repo_sha']}`. License: CC BY 4.0.

We have released everything from this study that does not expose SuperTruth's intellectual property. Released here:
all 20,000 synthetic Data Trust Index (DTI) records with the text the engine read, the scoring context, the
generator's knobs and the 65-float feature vector; all DTI engine labels for all 20,000 records (eight dimensions,
composite, tier, flags); the DTI-trained parameters of the five finished seed-1 arms; and all 20,000 synthetic
Behavioral Integrity Index (BII) event windows with their events and 58-float feature vectors. Held: the BII scores
and gates, the BII-trained parameters and the BII feature specification, because {HELD_BII} The two teacher engines
(the DTI scoring module and the VIGIL detection code) are not released. Anyone interested in what is held can write
to jas@supertruth.ai; we work with researchers.

Every record is synthetic; no real person's data was used. No protected health information exists in this dataset by
construction: every record is rendered by code from a seed, patient names are `SYN-` tokens, identifiers are `SYN`
strings, provider surnames are synthetic, file paths start with `/syn/`. The corpora are not calibrated to any real
population and nothing here claims they resemble real health data or real agent traffic.

## Files

{table(["File", "Rows", "What it is"], [
    ("dti_records.jsonl.gz", f"{N:,}", "DTI inputs: text, scoring context, knobs, features, split, model-arm flag. No label key."),
    ("dti_labels.jsonl.gz", f"{N:,}", "DTI engine labels for every record: dimensions, composite, tier, flags, split, model-arm flag."),
    ("bii_windows.jsonl.gz", f"{N:,}", "BII inputs: event lists, event counts, features, split. No score, gate, signal or knob key."),
    ("dti_weights_seed1.tar.gz", "15 members", "best.safetensors, run.json, standardization.json for the five DTI seed-1 arms."),
    ("splits.json", "", "train/val/test ids for both corpora, the 300 model-arm ids, and the split scheme."),
    ("MANIFEST.json", "", "sha256, bytes and row count of every file in this deposit."),
    ("zenodo-dataset.json", "", "the deposit metadata."),
])}

Each `.jsonl.gz` is gzip (mtime 0) over one JSON object per line, UTF-8, no trailing spaces. Integrity: compare
`MANIFEST.json` with `shasum -a 256`.

## How the records were generated

Both corpora were generated on 2026-09-20 with seed {SEED}, one independent draw per row, by the generators in the
code repository ({REPO_URL}, MIT):

- **DTI**, `teachers/gen_dti.ts` at commit `{ctx['gen_dti_sha']}`. Row i gets its own random stream, sfc32 seeded by
  xmur3(`"{SEED}|SYN-DTI-<i:06d>"`). The generator draws 40 knobs (the `knobs` object), renders a record text in one
  of seven templates, builds the scoring context (`element_scores`, `source_consent`, `consent_scope`), and hands text
  and context to the deployed DTI engine. The engine reads the wall clock for recency and consent age; it was frozen
  at `{FROZEN_CLOCK}` (epoch ms 1789948800000) for every call, so every label and every day-count feature is
  reproducible.
- **BII**, `teachers/gen_bii.py` at commit `{ctx['gen_bii_sha']}`. Row i uses `numpy.random.default_rng([{SEED}, i])`.
  The generator draws latent degradation parameters (held), builds a window of up to 50 events of each of four types
  as the live service trims, and hands the window to the scorer. No detector reads the clock.

The generators are released with the code; the DTI features and labels and the BII labels come from the teacher
engines, which are not, so a reader can regenerate the DTI knobs and text and the BII events from the seed but not
re-score them. The sha256 of each source file and the QA that regenerated slices of both files byte for byte are in
`teachers/MANIFEST.md` in the code repository.

## Labels

DTI labels are the outputs of the DEPLOYED DTI engine, the scoring module behind `POST https://supertruth.ai/api/v1/score`,
called in process at engine commit `{DTI_ENGINE_SHA}` with its default weights (Provenance 25, Consent 20, Recency 15,
Quality 10, Concordance 10, Validation 10, Breadth 5, Stability 5) and the clock frozen as above. They are not a
reimplementation. All 20,000 are released. The engine's per-dimension explanatory notes and its intermediate extracted
fields are not included (they describe the engine's internals). Tier counts: {tier_line}.

BII labels (score and gate), the five detector signals and their statistics, and the generator's latent parameters are
withheld from every file in this deposit: {HELD_BII} The BII teacher was the VIGIL detection code at commit
`{BII_ENGINE_SHA}` under its seed policy; each gate state holds at least 8% of windows (teachers/MANIFEST.md).

The 300 records flagged `in_model_arm_300` are the identical records scored by the four language-model arms of the
paper (Claude Opus 5, GPT-5, Grok 4, Gemini 3 Flash); all 300 are in the DTI test split.

## Splits

One fixed partition per corpus: {dti_split['scheme']}. Fractions 70/10/20, split seed
{dti_split['split_seed']}, stratified on `{dti_split['stratify_on']}` (DTI) and `{bii_split['stratify_on']}` (BII).
DTI: train {dti_split['counts']['train']['total']:,}, val {dti_split['counts']['val']['total']:,}, test {dti_split['counts']['test']['total']:,}.
BII: train {bii_split['counts']['train']['total']:,}, val {bii_split['counts']['val']['total']:,}, test {bii_split['counts']['test']['total']:,}.
`splits.json` carries the id lists under `dti.train`, `dti.val`, `dti.test`, `dti.model_arm_300`, `bii.train`, `bii.val`,
`bii.test`, and the same scheme fields. The `split` column on every row is the same membership.

## Columns

### dti_records.jsonl.gz

{table(["Column", "Type", "Range or values", "Meaning"], DTI_RECORD_COLUMNS)}

`knobs` fields:

{table(["Knob", "Type and range", "Meaning"], DTI_KNOBS)}

### dti_labels.jsonl.gz

{table(["Column", "Type", "Range or values", "Meaning"], DTI_LABEL_COLUMNS)}

### bii_windows.jsonl.gz

{table(["Column", "Type", "Range or values", "Meaning"], BII_WINDOW_COLUMNS)}

`events.<type>[k].payload` keys by type:

{table(["Event type", "Payload"], BII_PAYLOADS)}

## Feature vectors

**DTI (65 floats).** Built only from what the engine reads: its extracted-field structure plus the scoring context.
Nothing from the label side enters the vector. Day counts use the frozen clock. The full specification with the
meaning of each slot is `teachers/dti_features_spec.md` in the code repository; index, name and range:

{table(["idx", "name", "range"], [(i, f"`{n}`", rg) for i, n, _m, rg in feat])}

**BII (58 floats).** Built only from the event window (payloads and each event's `monitored_at_time`). The vector is
released; its specification is held for the reason stated above. Values lie in 0 .. about 1.5.

## Trained parameters (dti_weights_seed1.tar.gz)

The DTI-trained parameters of the five finished seed-1 arms of the paper. They reproduce the DEPLOYED DTI engine's
behaviour on synthetic records of this distribution to the accuracy in the table below (test split, 4,001 records,
from each arm's metrics.json; Section 4 of the paper) and are released under CC BY 4.0 like everything else in this
deposit. They are students of the engine, not the engine. Each arm directory holds `best.safetensors` (the state dict at the
best validation epoch), `run.json` (every setting, the split and standardization provenance, the training history)
and `standardization.json` (per-feature mean and std fit on the training split only).

{table(["Arm", "Substrate", "Trainable parameters", "Best epoch", "Composite error (points)", "Tier agreement", "Notes", "Code commit"], arm_table_rows())}

To load an arm, install the code repository ({REPO_URL}) and build the derived graph once
(`data/build_graph.py --threshold 5` over MaleCNS v1.0, CC BY 4.0, HHMI Janelia; `graph_meta.json` sha256
`{ctx['graph_meta_sha']}`). The connectome, shuffle and random-graph arms need the graph; the shuffle and
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
run = json.load(open(f"dti_weights_seed1/{{arm}}/run.json"))
cfg = run["config"]
kw = {{"norm": cfg["norm"]}} if arm in ("connectome", "shuffle", "er") else {{}}
if arm == "shuffle":
    kw["swaps_per_edge"] = cfg["extra"]["swaps_per_edge"]
if arm == "ridge":
    kw = {{"lam": cfg["ridge_lambda"]}}
model, _ = build_arm(arm, graph, 65, DTI_SPEC, T=cfg["T"], device="cpu", seed=cfg["seed"], **kw)
model.load_state_dict(load_file(f"dti_weights_seed1/{{arm}}/best.safetensors"))
model.eval()
scaler = Standardizer.load(f"dti_weights_seed1/{{arm}}/standardization.json")

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

Dataset: Snyder, J. A. (2026). {DATASET_TITLE} [Data set]. Zenodo. [DATASET DOI]

Paper: Snyder, J. A. (2026). {PAPER_TITLE}. Zenodo. [PAPER DOI]

The DTI framework the engine implements: Snyder, J. A. (2026). The Data Trust Index: A Multidimensional Framework for
Evaluating Health Data Integrity in AI Systems. Zenodo. https://doi.org/10.5281/zenodo.19601616

Data Trust Index is a trademark of SuperTruth Inc. DTI and BII score data records and software-agent behaviour; they
do not diagnose, treat, or make recommendations about any patient.
"""


def render_zenodo(ctx: dict) -> dict:
    return {
        "_note": "Zenodo deposit metadata for the dataset record. Replace [PAPER DOI] with the paper record's DOI before deposit; JAS uploads.",
        "metadata": {
            "upload_type": "dataset",
            "title": DATASET_TITLE,
            "creators": [{"name": "Snyder, Jason Alan", "affiliation": "SuperTruth Inc.", "orcid": "0009-0001-6157-8100"}],
            "description": (
                f"Two synthetic corpora of 20,000 rows each, generated with seed {SEED} for the connectome substrate study "
                f"'{PAPER_TITLE}'. DTI: every record's text, scoring context, generator knobs and 65-float feature vector, "
                f"with the deployed Data Trust Index engine's labels (eight dimensions, composite, tier, flags) for all 20,000 "
                f"records at engine commit {DTI_ENGINE_SHA[:8]} with the clock frozen at {FROZEN_CLOCK}, the train/val/test split, "
                f"a flag on the 300 records scored by the four language-model arms, and the DTI-trained parameters of the five "
                f"seed-1 arms (fly wiring, degree-preserving shuffle, random graph, parameter-matched network, ridge readout). "
                f"BII: every event window's events and 58-float feature vector with the split. The BII scores and gates, the "
                f"BII-trained parameters and the BII feature specification are held: {HELD_BII} "
                f"The teacher engines are not released. Every record is synthetic; no real person's data was used. "
                f"Files, columns, generation and loading are documented in README.md; sha256 of every file in MANIFEST.json."
            ),
            "access_right": "open",
            "license": "cc-by-4.0",
            "publication_date": ctx["date"],
            "language": "eng",
            "version": "1.0",
            "keywords": ["synthetic data", "health records", "data trust", "Data Trust Index", "Behavioral Integrity Index",
                         "agent event logs", "connectome", "Drosophila", "MaleCNS", "fixed-substrate learning",
                         "teacher labels", "trained parameters"],
            "related_identifiers": [
                {"identifier": "[PAPER DOI]", "relation": "isSupplementTo", "resource_type": "publication-workingpaper", "scheme": "doi"},
                {"identifier": "10.5281/zenodo.19601616", "relation": "cites", "resource_type": "publication-workingpaper", "scheme": "doi"},
                {"identifier": REPO_URL, "relation": "isSupplementTo", "resource_type": "software", "scheme": "url"},
            ],
            "notes": (
                f"Every record is synthetic; no real person's data was used. Released: all 20,000 DTI records, features and "
                f"engine labels, the DTI-trained seed-1 parameters, all 20,000 BII windows and features. Held: BII scores and "
                f"gates, BII-trained parameters and the BII feature specification, because {HELD_BII} The DTI and BII teacher "
                f"engines are not released. isDerivedFrom: none; the records are generated by code from a seed, not derived "
                f"from any dataset. DTI and BII score data records and software-agent behaviour; they do not diagnose, treat, "
                f"or make recommendations about any patient."
            ),
        },
    }


# ── verification ────────────────────────────────────────────────────────────────
def readme_columns(readme: str, heading: str) -> list:
    """Column names listed in the README table under `### <heading>`."""
    sec = readme.split(f"### {heading}\n", 1)[1].split("\n###", 1)[0].split("\n\n`", 1)[0]
    return [m.group(1) for m in re.finditer(r"^\| ([a-z_0-9]+) \| ", sec, flags=re.M)]


def key_scan(blob: bytes, keys, scalar_only: bool = False) -> list:
    """Keys present as JSON object keys. scalar_only=True (metadata files) counts a key only when its value is a scalar
    (number, string, null, bool): a leaked label is `"bii": 0.85` or `"gate": "pass"`, while `"bii": {...}` is one of this
    deposit's own section containers (splits.json, MANIFEST.json)."""
    found = []
    tail = rb'\s*:\s*(?:-?\d|"|null|true|false)' if scalar_only else rb'\s*:'
    for k in keys:
        if re.search(rb'(?<!\\)"' + k.encode() + rb'"' + tail, blob):
            found.append(k)
    return found


def verify(out: Path, ctx: dict, readme: str) -> dict:
    rep = {}
    splits = json.loads((out / "splits.json").read_text())
    arm_ids = set(splits["dti"]["model_arm_300"])
    dti_member = {rid: p for p in ("train", "val", "test") for rid in splits["dti"][p]}
    bii_member = {rid: p for p in ("train", "val", "test") for rid in splits["bii"][p]}
    if len(arm_ids) != N_MODEL_ARM or any(dti_member[r] != "test" for r in arm_ids):
        raise SystemExit("splits.json: the 300 model-arm ids are not all in test")

    def read_gz(name: str, expect_cols: list, id_field: str, member: dict, forbidden) -> dict:
        blob = gzip.decompress((out / name).read_bytes())
        leaked = key_scan(blob, forbidden)
        if leaked:
            raise SystemExit(f"{name}: forbidden key(s) present: {leaked}")
        n, flagged, ids, split_ct = 0, 0, set(), Counter()
        for line in blob.split(b"\n"):
            if not line:
                continue
            r = json.loads(line)
            if list(r.keys()) != expect_cols:
                raise SystemExit(f"{name}: keys {list(r.keys())} != README columns {expect_cols}")
            if r["split"] != member[r[id_field]]:
                raise SystemExit(f"{name}: {r[id_field]} split column disagrees with splits.json")
            ids.add(r[id_field])
            split_ct[r["split"]] += 1
            flagged += bool(r.get("in_model_arm_300", False))
            n += 1
        if n != N or len(ids) != N:
            raise SystemExit(f"{name}: {n} rows, {len(ids)} unique ids")
        return {"rows": n, "flagged_300": flagged, "split_counts": dict(split_ct), "leaked_keys": leaked, "ids": ids}

    rec = read_gz("dti_records.jsonl.gz", readme_columns(readme, "dti_records.jsonl.gz"), "record_id", dti_member, DTI_LABEL_KEYS + BII_LABEL_KEYS)
    lab = read_gz("dti_labels.jsonl.gz", readme_columns(readme, "dti_labels.jsonl.gz"), "record_id", dti_member, BII_LABEL_KEYS)
    bii = read_gz("bii_windows.jsonl.gz", readme_columns(readme, "bii_windows.jsonl.gz"), "window_id", bii_member, BII_LABEL_KEYS + BII_HELD_INPUT_KEYS)
    if rec["flagged_300"] != N_MODEL_ARM or lab["flagged_300"] != N_MODEL_ARM:
        raise SystemExit("in_model_arm_300 count is not 300")
    if rec["ids"] != lab["ids"]:
        raise SystemExit("dti_records and dti_labels do not carry the same ids")
    flagged_ids = set()
    for line in gzip.decompress((out / "dti_labels.jsonl.gz").read_bytes()).split(b"\n"):
        if line:
            r = json.loads(line)
            if r["in_model_arm_300"]:
                flagged_ids.add(r["record_id"])
    if flagged_ids != arm_ids:
        raise SystemExit("flagged ids != the 300 model-arm ids")
    for d in (rec, lab, bii):
        d.pop("ids")
    rep.update({"dti_records": rec, "dti_labels": lab, "bii_windows": bii})

    # BII label keys must appear in NO released text file (README, MANIFEST, zenodo, splits, run.json inside the tar)
    for name in ("README.md", "MANIFEST.json", "zenodo-dataset.json", "splits.json"):
        leaked = key_scan((out / name).read_bytes(), BII_LABEL_KEYS, scalar_only=True)
        if leaked:
            raise SystemExit(f"{name}: BII label key(s) present as JSON keys: {leaked}")
    with tarfile.open(out / "dti_weights_seed1.tar.gz", "r:gz") as tar:
        names = sorted(tar.getnames())
        expect = sorted(f"dti_weights_seed1/{a}/{f}" for a in ARMS for f in WEIGHT_FILES)
        if names != expect:
            raise SystemExit(f"tar members {names} != {expect}")
        for m in tar.getmembers():
            if m.name.endswith(".json"):
                leaked = key_scan(tar.extractfile(m).read(), BII_LABEL_KEYS)
                if leaked:
                    raise SystemExit(f"{m.name}: BII label key(s) present: {leaked}")
    rep["tar_members"] = len(names)
    return rep


def verify_weights(out: Path, n_rows: int = 16) -> dict:
    """Rebuild each arm from the packaged tarball with the packaged features; compare with the recorded test predictions."""
    import tempfile
    import numpy as np
    import pandas as pd
    import torch
    from safetensors.torch import load_file
    from flytrust.graph import load_graph
    from flytrust.model import DTI_SPEC, TIERS
    from flytrust.controls import build_arm
    from flytrust.data_adapters import Standardizer

    with tempfile.TemporaryDirectory() as td:
        with tarfile.open(out / "dti_weights_seed1.tar.gz", "r:gz") as tar:
            tar.extractall(td, filter="data")
        base = Path(td) / "dti_weights_seed1"
        feats = {}
        for line in gzip.decompress((out / "dti_records.jsonl.gz").read_bytes()).split(b"\n"):
            if line:
                r = json.loads(line)
                feats[r["record_id"]] = r["features"]
        graph = load_graph()
        results = {}
        for arm in ARMS:
            run = json.loads((base / arm / "run.json").read_text())
            cfg = run["config"]
            kw = {"norm": cfg["norm"]} if arm in ("connectome", "shuffle", "er") else {}
            if arm == "shuffle":
                kw["swaps_per_edge"] = cfg["extra"]["swaps_per_edge"]
            if arm == "ridge":
                kw = {"lam": cfg["ridge_lambda"]}
            model, _ = build_arm(arm, graph, 65, DTI_SPEC, T=cfg["T"], device="cpu", seed=cfg["seed"], **kw)
            model.load_state_dict(load_file(str(base / arm / "best.safetensors")))
            model.eval()
            scaler = Standardizer.load(base / arm / "standardization.json")
            per = pd.read_parquet(ROOT / "runs" / "dti" / arm / "seed1" / "per_record.parquet").head(n_rows)
            X = torch.tensor([feats[r] for r in per["record_id"]], dtype=torch.float32)
            with torch.no_grad():
                o = model(scaler.transform(X))
            dims = np.clip(o["dims"].numpy() * 100, 0, 100)     # as scripts/eval_subset.py per_record_table clips
            comp = o["composite"].numpy().ravel() * 100
            tiers = [TIERS[i] for i in o["tier"].argmax(1).tolist()]
            ref = per[["provenance_pred", "consent_pred", "recency_pred", "quality_pred", "concordance_pred",
                       "validation_pred", "breadth_pred", "stability_pred"]].to_numpy()
            results[arm] = {"n": int(n_rows), "max_abs_diff_dims": float(np.abs(dims - ref).max()),
                            "max_abs_diff_composite": float(np.abs(comp - per["composite_pred_direct"].to_numpy()).max()),
                            "tier_agreement": int(sum(t == p for t, p in zip(tiers, per["tier_pred"])))}
            del model
        return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "dataset")
    ap.add_argument("--verify-weights", action="store_true", help="rebuild every arm from the tarball and compare with per_record.parquet")
    a = ap.parse_args(argv)
    out = a.out
    out.mkdir(parents=True, exist_ok=True)

    # 1. sources match teachers/MANIFEST.md
    want = manifest_hashes()
    src_sha = {t: sha256_file(ROOT / "teachers" / f"{t}_teacher.jsonl") for t in ("dti", "bii")}
    for t in ("dti", "bii"):
        if src_sha[t] != want[t]:
            raise SystemExit(f"teachers/{t}_teacher.jsonl sha256 {src_sha[t]} != MANIFEST.md {want[t]}")
    dti_split, bii_split = load_split("dti"), load_split("bii")
    arm_ids = model_arm_ids()
    if any(dti_split["member"][r] != "test" for r in arm_ids):
        raise SystemExit("a model-arm record is not in the DTI test split")

    ctx = {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "repo_sha": git("rev-parse", "HEAD"),
        "gen_dti_sha": git("log", "-1", "--format=%H", "--", "teachers/gen_dti.ts"),
        "gen_bii_sha": git("log", "-1", "--format=%H", "--", "teachers/gen_bii.py"),
        "graph_meta_sha": json.loads((ROOT / "runs" / "dti" / "connectome" / "seed1" / "run.json").read_text())["graph_meta_sha256"],
        "dti_split": dti_split, "bii_split": bii_split,
    }

    # 2. data files
    ctx["dti"] = write_dti(out, dti_split["member"], set(arm_ids))
    ctx["bii"] = write_bii(out, bii_split["member"])
    (out / "splits.json").write_text(json.dumps({
        "dti": {**dti_split["meta"], **dti_split["parts"], "model_arm_300": arm_ids,
                "model_arm_source": {"run": LLM_RUN.name, "calls_sha256": sha256_file(LLM_RUN / "calls.jsonl")}},
        "bii": {**bii_split["meta"], **bii_split["parts"]},
    }, indent=1) + "\n")
    tar_members = write_weights_tar(out)

    # 3. docs and metadata (README first: MANIFEST hashes it)
    readme = render_readme(ctx)
    (out / "README.md").write_text(readme)
    (out / "zenodo-dataset.json").write_text(json.dumps(render_zenodo(ctx), indent=2, ensure_ascii=False) + "\n")
    files = {}
    for name, rows in (("dti_records.jsonl.gz", N), ("dti_labels.jsonl.gz", N), ("bii_windows.jsonl.gz", N),
                       ("dti_weights_seed1.tar.gz", None), ("splits.json", None), ("README.md", None), ("zenodo-dataset.json", None)):
        p = out / name
        files[name] = {"bytes": p.stat().st_size, "sha256": sha256_file(p)}
        if rows is not None:
            files[name]["rows"] = rows
        if name == "dti_weights_seed1.tar.gz":
            files[name]["members"] = tar_members
    manifest = {
        "title": DATASET_TITLE, "version": "1.0", "license": "CC-BY-4.0", "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo": REPO_URL, "repo_commit": ctx["repo_sha"], "generator_commits": {"gen_dti.ts": ctx["gen_dti_sha"], "gen_bii.py": ctx["gen_bii_sha"]},
        "seed": SEED, "frozen_clock": FROZEN_CLOCK, "engine_commits": {"dti": DTI_ENGINE_SHA, "bii_vigil": BII_ENGINE_SHA},
        "sources": {"teachers/dti_teacher.jsonl": src_sha["dti"], "teachers/bii_teacher.jsonl": src_sha["bii"],
                    "splits/dti_seed1.json": sha256_file(ROOT / "splits" / "dti_seed1.json"), "splits/bii_seed1.json": sha256_file(ROOT / "splits" / "bii_seed1.json"),
                    f"llm_arm/llm_runs/{LLM_RUN.name}/calls.jsonl": sha256_file(LLM_RUN / "calls.jsonl")},
        "released": {"dti_corpus": "records, features, all 20,000 engine labels, trained parameters (seed 1, five arms)", "bii_corpus": "windows and features"},
        "held": {"bii_corpus": f"scores and gates, trained parameters, feature specification: {HELD_BII}", "engines": "the DTI scoring module and the VIGIL detection code are not released"},
        "files": files,
    }
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")

    # 4. verification and adversarial pass
    rep = verify(out, ctx, readme)
    if a.verify_weights:
        rep["weights"] = verify_weights(out)

    print(json.dumps({"files": {k: {kk: vv for kk, vv in v.items() if kk != "members"} for k, v in files.items()},
                      "verification": rep, "repo_commit": ctx["repo_sha"]}, indent=1))
    print("OK")


if __name__ == "__main__":
    main()
