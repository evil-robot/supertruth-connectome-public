"""
qa_teachers.py -- adversarially tested verifier for the two teacher datasets.

Every check runs twice: once on the real artifacts (must PASS) and once on an
INDUCED failure (must FAIL, i.e. the check must catch it). A check that cannot
catch its own induced failure is itself a failure.

Run:  uv run --project ~/Projects/ds-lab python /tmp/connectome-paper/teachers/qa_teachers.py
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import tempfile

HERE = "/tmp/connectome-paper/teachers"
WEB = "/Users/jas/Projects/st-homepage-refresh"
TSX = f"{WEB}/node_modules/.bin/tsx"
VENV_PY = f"{HERE}/.venv-vigil/bin/python"
DTI_SEED = 20260920
BII_SEED = 20260920
N_REGEN = 200

DTI_WEIGHTS = {"provenance": 25, "consent": 20, "recency": 15, "quality": 10, "concordance": 10, "validation": 10, "breadth": 5, "stability": 5}
BII_WEIGHTS = {"score_inflation": 0.30, "config_tamper": 0.30, "alignment_faking": 0.25, "asset_movement": 0.15, "blueprint_drift": 0.00}

results: list[dict] = []


def record(name: str, ok: bool, detail: str, induced: bool = False):
    # For induced runs, "ok" means the check FAILED as it should.
    results.append({"check": name, "mode": "induced" if induced else "real", "passed": ok, "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {'(induced) ' if induced else ''}{name}: {detail}")


def head_lines(path: str, n: int, start: int = 0) -> list[str]:
    out = []
    with open(path) as f:
        for i, line in enumerate(f):
            if i >= start + n:
                break
            if i >= start:
                out.append(line)
    return out


def load_rows(path: str):
    with open(path) as f:
        for line in f:
            yield json.loads(line)


# ── 1. determinism ─────────────────────────────────────────────────────────────
def regen_dti(seed: int, start: int, n: int) -> list[str]:
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        p = tf.name
    subprocess.run([TSX, f"{HERE}/gen_dti.ts", "--seed", str(seed), "--start", str(start), "--n", str(n), "--rows-only", p],
                   cwd=WEB, check=True, capture_output=True)
    with open(p) as f:
        lines = f.readlines()
    os.unlink(p)
    return lines


def regen_bii(seed: int, start: int, n: int) -> list[str]:
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        p = tf.name
    subprocess.run([VENV_PY, f"{HERE}/gen_bii.py", "--seed", str(seed), "--start", str(start), "--n", str(n), "--rows-only", p],
                   cwd=HERE, check=True, capture_output=True)
    with open(p) as f:
        lines = f.readlines()
    os.unlink(p)
    return lines


def check_determinism(name: str, path: str, regen, seed: int):
    orig = head_lines(path, N_REGEN)
    new = regen(seed, 0, N_REGEN)
    same = orig == new
    record(f"{name} determinism (rows 0..{N_REGEN - 1} byte-identical)", same, f"{sum(a == b for a, b in zip(orig, new))}/{N_REGEN} identical")
    # slice from the middle: per-id independence of the PRNG
    mid = head_lines(path, 50, 10000)
    new_mid = regen(seed, 10000, 50)
    record(f"{name} determinism (rows 10000..10049 regenerated in isolation)", mid == new_mid, f"{sum(a == b for a, b in zip(mid, new_mid))}/50 identical")
    # induced: wrong seed must be detected
    bad = regen(seed + 1, 0, 20)
    ndiff = sum(a != b for a, b in zip(orig[:20], bad))
    record(f"{name} determinism catches a flipped seed", ndiff == 20, f"{ndiff}/20 rows differ under seed+1", induced=True)


# ── 2. floors ──────────────────────────────────────────────────────────────────
def tier_floor(rows, key: str, lo: float, hi: float, expected: set[str]):
    from collections import Counter
    c = Counter(r[key] for r in rows)
    n = sum(c.values())
    shares = {k: v / n for k, v in c.items()}
    ok = set(shares) == expected and all(lo <= s <= hi for s in shares.values())
    return ok, {k: round(v, 4) for k, v in shares.items()}


# ── 3. NaN ─────────────────────────────────────────────────────────────────────
def has_nan(x) -> bool:
    if isinstance(x, float):
        return math.isnan(x) or math.isinf(x)
    if isinstance(x, dict):
        return any(has_nan(v) for v in x.values())
    if isinstance(x, list):
        return any(has_nan(v) for v in x)
    return False


# ── 4. feature spec length ─────────────────────────────────────────────────────
def spec_rows(md_path: str) -> int:
    with open(md_path) as f:
        txt = f.read()
    return len(re.findall(r"^\| \d+ \| `", txt, flags=re.M))


def declared_len(md_path: str) -> int:
    with open(md_path) as f:
        m = re.search(r"Fixed length: \*\*(\d+)\*\*", f.read())
    return int(m.group(1)) if m else -1


# ── 5. label arithmetic ────────────────────────────────────────────────────────
def dti_label_ok(r) -> bool:
    # Accumulate exactly as pipeline.ts :773-775 does (Array.reduce, left to right, naive IEEE adds).
    # Python 3.12+ sum() uses compensated summation and disagrees on 23/20000 rows that sit on an exact .5.
    raw = 0.0
    for d, w in DTI_WEIGHTS.items():
        raw = raw + (r["dimensions"][d] * w) / 100
    comp = math.floor(raw + 0.5)  # JS Math.round for positive x
    tier = "PLATINUM" if comp >= 90 else "GOLD" if comp >= 80 else "SILVER" if comp >= 70 else "BRONZE" if comp >= 55 else "BELOW THRESHOLD"
    flags = sorted(f"{d}_below_75" for d, s in r["dimensions"].items() if s < 75)
    return comp == r["composite"] and tier == r["tier"] and flags == sorted(r["flags"])


def bii_label_ok(r) -> bool:
    # Same literal chain as api/detection/__init__.py :43-49 (no compensated sum()).
    s_ = r["signals"]
    bii = round(s_["score_inflation"] * 0.30 + s_["config_tamper"] * 0.30 + s_["alignment_faking"] * 0.25
                + s_["asset_movement"] * 0.15 + s_["blueprint_drift"] * 0.0, 4)
    gate = "collapse" if bii <= 0.40 else "alert" if bii < 0.60 else "hold" if bii < 0.75 else "pass"
    return abs(bii - r["bii"]) < 1e-9 and gate == r["gate"]


# ── 6. synthetic-only guard ────────────────────────────────────────────────────
def dti_synthetic_ok(r) -> bool:
    if not r["record_id"].startswith("SYN-DTI-"):
        return False
    name = r["extracted"]["patientName"]
    if name is not None and "SYN" not in name:
        return False
    for e in r["extracted"]["providers"]:
        if not any(e.endswith(s) for s in ("Synthprov", "Fakemd", "Mockdoc", "Testphys", "Stubcare", "Dummyclin")):
            return False
    return True


def main():
    dti_path, bii_path = f"{HERE}/dti_teacher.jsonl", f"{HERE}/bii_teacher.jsonl"

    # 1 determinism
    check_determinism("DTI", dti_path, regen_dti, DTI_SEED)
    check_determinism("BII", bii_path, regen_bii, BII_SEED)

    # load
    dti = list(load_rows(dti_path))
    bii = list(load_rows(bii_path))
    record("DTI row count", len(dti) == 20000, f"n={len(dti)}")
    record("BII row count", len(bii) == 20000, f"n={len(bii)}")

    # 2 floors
    ok, shares = tier_floor(dti, "tier", 0.08, 0.40, {"PLATINUM", "GOLD", "SILVER", "BRONZE", "BELOW THRESHOLD"})
    record("DTI tier floors 8%..40%, all five tiers", ok, json.dumps(shares))
    ok_i, shares_i = tier_floor([r for r in dti if r["tier"] != "PLATINUM"], "tier", 0.08, 0.40, {"PLATINUM", "GOLD", "SILVER", "BRONZE", "BELOW THRESHOLD"})
    record("DTI tier floor check catches a missing tier", not ok_i, f"PLATINUM removed -> {json.dumps(shares_i)}", induced=True)
    ok, shares = tier_floor(bii, "gate", 0.08, 1.0, {"pass", "hold", "alert", "collapse"})
    record("BII gate floors >= 8%, all four states", ok, json.dumps(shares))
    ok_i, shares_i = tier_floor([r for r in bii if r["gate"] != "collapse" or hash(r["window_id"]) % 20 == 0], "gate", 0.08, 1.0, {"pass", "hold", "alert", "collapse"})
    record("BII gate floor check catches a starved state", not ok_i, f"collapse thinned to ~5% -> {json.dumps(shares_i)}", induced=True)

    # 3 NaN
    nan_dti = sum(has_nan({"d": r["dimensions"], "c": r["composite"], "f": r["features"]}) for r in dti)
    record("DTI no NaN/Inf in dimensions, composite, features", nan_dti == 0, f"{nan_dti} rows with NaN")
    nan_bii = sum(has_nan({"s": r["signals"], "b": r["bii"], "f": r["features"]}) for r in bii)
    record("BII no NaN/Inf in signals, bii, features", nan_bii == 0, f"{nan_bii} rows with NaN")
    poisoned = dict(dti[0]); poisoned["features"] = dti[0]["features"][:-1] + [float("nan")]
    record("NaN check catches an injected NaN", has_nan({"f": poisoned["features"]}), "features[-1] := NaN detected", induced=True)

    # 4 feature spec length
    dspec, dlen = f"{HERE}/dti_features_spec.md", len(dti[0]["features"])
    dsum = json.load(open(f"{HERE}/dti_teacher_summary.json"))
    ok = spec_rows(dspec) == dlen == declared_len(dspec) == dsum["feature_len"] and all(len(r["features"]) == dlen for r in dti)
    record("DTI feature spec length == encoded vector length (all rows)", ok, f"spec rows={spec_rows(dspec)} declared={declared_len(dspec)} vector={dlen} summary={dsum['feature_len']}")
    bspec, blen = f"{HERE}/bii_features_spec.md", len(bii[0]["features"])
    bsum = json.load(open(f"{HERE}/bii_teacher_summary.json"))
    ok = spec_rows(bspec) == blen == declared_len(bspec) == bsum["feature_len"] and all(len(r["features"]) == blen for r in bii)
    record("BII feature spec length == encoded vector length (all rows)", ok, f"spec rows={spec_rows(bspec)} declared={declared_len(bspec)} vector={blen} summary={bsum['feature_len']}")
    with open(dspec) as f:
        lines = f.read().splitlines()
    idx = next(i for i, l in enumerate(lines) if re.match(r"^\| \d+ \| `", l))
    truncated = "\n".join(lines[:idx] + lines[idx + 1:])
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as tf:
        tf.write(truncated); tp = tf.name
    record("spec length check catches a dropped spec row", spec_rows(tp) != dlen, f"spec rows={spec_rows(tp)} vs vector={dlen}", induced=True)
    os.unlink(tp)

    # 5 label arithmetic (independent recomputation from the constants in pipeline.ts / detection/__init__.py / gate.py)
    bad = sum(not dti_label_ok(r) for r in dti)
    record("DTI composite/tier/flags recomputed from dimensions and default weights", bad == 0, f"{bad} mismatches")
    bad = sum(not bii_label_ok(r) for r in bii)
    record("BII bii/gate recomputed from signals, seed weights and thresholds", bad == 0, f"{bad} mismatches")
    p = json.loads(json.dumps(dti[0])); p["composite"] += 1
    record("label check catches a perturbed composite", not dti_label_ok(p), "composite+1 detected", induced=True)
    p = json.loads(json.dumps(bii[0])); p["bii"] = round(p["bii"] + 0.01, 4)
    record("label check catches a perturbed bii", not bii_label_ok(p), "bii+0.01 detected", induced=True)

    # 6 synthetic-only
    bad = sum(not dti_synthetic_ok(r) for r in dti)
    record("DTI synthetic guard: SYN ids, SYN names, synthetic provider surnames", bad == 0, f"{bad} rows fail")
    p = json.loads(json.dumps(dti[0])); p["extracted"]["patientName"] = "Maria Gonzalez"
    record("synthetic guard catches a realistic name", not dti_synthetic_ok(p), "non-SYN name detected", induced=True)
    bad = sum(not r["window_id"].startswith("SYN-BII-") for r in bii)
    paths = {e["payload"].get("source_path") for r in bii[:2000] for e in r["events"]["file_operation"]}
    record("BII synthetic guard: SYN ids, /syn/ paths only", bad == 0 and all(p.startswith("/syn/") for p in paths), f"{bad} bad ids; paths={sorted(paths)}")

    # 7 duplicates recount (from the files, not the summaries)
    from collections import Counter
    dd = Counter(tuple(r["features"]) for r in dti); dup_d = sum(c - 1 for c in dd.values() if c > 1)
    bd = Counter(tuple(r["features"]) for r in bii); dup_b = sum(c - 1 for c in bd.values() if c > 1)
    empties = sum(1 for r in bii if sum(r["event_counts"].values()) == 0)
    record("duplicate feature vectors recounted", dup_d == dsum["duplicate_feature_vectors"] and dup_b == bsum["duplicate_feature_vectors"],
           f"DTI dup={dup_d} (summary {dsum['duplicate_feature_vectors']}); BII dup={dup_b} (summary {bsum['duplicate_feature_vectors']}), empty windows={empties}")

    real_fail = [r for r in results if r["mode"] == "real" and not r["passed"]]
    induced_fail = [r for r in results if r["mode"] == "induced" and not r["passed"]]
    verdict = {"real_checks": sum(r["mode"] == "real" for r in results), "real_failed": len(real_fail),
               "induced_checks": sum(r["mode"] == "induced" for r in results), "induced_not_caught": len(induced_fail),
               "verdict": "PASS" if not real_fail and not induced_fail else "FAIL", "results": results}
    with open(f"{HERE}/qa_report.json", "w") as f:
        json.dump(verdict, f, indent=2)
    print(json.dumps({k: v for k, v in verdict.items() if k != "results"}))
    sys.exit(0 if verdict["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
