"""Leakage and dataset-health gate for the teacher splits (DECISION_RULES.md, the tests that apply now).

Runs BEFORE any training. Every check prints PASS/FAIL; any FAIL -> exit 1 and no metric may be printed.
Writes splits/qa_report.json (the health checklist attached to every results table).

  .venv/bin/python scripts/qa_adversary.py                 # real checks on splits/{task}_seed1.json
  .venv/bin/python scripts/qa_adversary.py --self-test     # induced failures: each planted fault must go RED

Checks (rule numbers from DECISION_RULES.md):
  no_id_overlap            partitions disjoint, union = corpus, no unknown ids                    (rules 1, 2)
  stratified               every class share per partition within 1.0 pp of its corpus share
  no_duplicate_straddle    identical feature vectors never sit in two partitions                   (rules 1, 3)
  class_floors             DTI tier >= 8% / BII gate >= 10% in every partition; TEST support >= 30 (rule 18)
  id_not_predictive        max one-vs-rest AUROC of the id ordinal against the label <= 0.55     (rule 4)
  no_target_in_features    no output field name among feature names; max |corr(feature, target)| < 0.999 (rule 6)
Health (informational, printed and saved): counts per split per class, exact duplicates, missingness, imbalance,
multicollinearity (exact collinear columns, max VIF via pseudo-inverse), KS train-vs-test per target, top-10
feature-target correlations, degenerate targets (SD < 2.0 points DTI, < 0.02 BII; rule 8), constant features.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.stats import ks_2samp, rankdata

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flytrust.data_adapters import load_teacher, DTI_DIMS, LABEL_FIELD   # noqa: E402
from flytrust.graph import ROOT, sha256_file                              # noqa: E402

CLASS_FLOOR = {"dti": 0.08, "bii": 0.10}
DEGENERATE_SD = {"dti": 2.0 / 100.0, "bii": 0.02}       # targets are stored 0-1
OUTPUT_FIELDS = {
    "dti": set(DTI_DIMS) | {"composite", "tier", "flags", "dimension_notes", "dimensions"},
    "bii": {"bii", "gate", "gate_reason", "signals", "signal_stats", "score_inflation", "config_tamper",
            "alignment_faking", "asset_movement", "blueprint_drift"},
}
SPEC_FILE = {"dti": "teachers/dti_features_spec.md", "bii": "teachers/bii_features_spec.md"}


def feature_names(task: str) -> list[str]:
    rows = re.findall(r"^\|\s*(\d+)\s*\|\s*`([^`]+)`", (ROOT / SPEC_FILE[task]).read_text(), flags=re.M)
    names = [n for _, n in sorted(rows, key=lambda t: int(t[0]))]
    return names


def targets_matrix(task: str, Y: dict) -> tuple[np.ndarray, list[str]]:
    if task == "dti":
        return np.concatenate([Y["dims"].numpy(), Y["composite"].numpy()], 1), DTI_DIMS + ["composite"]
    return Y["bii"].numpy(), ["bii"]


def auroc_binary(score: np.ndarray, pos: np.ndarray) -> float:
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return 0.5
    r = rankdata(score)
    return float((r[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


# ------------------------------------------------------------------ checks (each returns (ok, detail))
def check_no_id_overlap(split: dict, ids: list[str]):
    parts = {p: set(split[p]) for p in ("train", "val", "test")}
    overlap = {f"{a}&{b}": len(parts[a] & parts[b]) for a in parts for b in parts if a < b}
    union = set().union(*parts.values())
    unknown = len(union - set(ids))
    missing = len(set(ids) - union)
    dup_within = sum(len(split[p]) - len(parts[p]) for p in parts)
    ok = all(v == 0 for v in overlap.values()) and unknown == 0 and missing == 0 and dup_within == 0
    return ok, {"overlap": overlap, "unknown_ids": unknown, "missing_ids": missing, "duplicate_within_partition": dup_within}


def check_stratified(split: dict, ids: list[str], labels: list[str], tol_pp: float = 1.0):
    lab = dict(zip(ids, labels))
    corpus = Counter(labels)
    n = len(labels)
    worst, detail = 0.0, {}
    for p in ("train", "val", "test"):
        c = Counter(lab[r] for r in split[p])
        for cls in corpus:
            d = 100 * abs(c[cls] / len(split[p]) - corpus[cls] / n)
            detail[f"{p}:{cls}"] = round(d, 3)
            worst = max(worst, d)
    return worst <= tol_pp, {"max_abs_share_diff_pp": round(worst, 3), "tolerance_pp": tol_pp}


def check_no_duplicate_straddle(split: dict, ids: list[str], X: np.ndarray):
    part = {r: p for p in ("train", "val", "test") for r in split[p]}
    _, inv, cnt = np.unique(X, axis=0, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    straddle = 0
    for g in np.flatnonzero(cnt > 1):
        rows = np.flatnonzero(inv == g)
        if len({part[ids[i]] for i in rows}) > 1:
            straddle += 1
    return straddle == 0, {"duplicate_groups": int((cnt > 1).sum()), "rows_in_duplicate_groups": int(cnt[cnt > 1].sum()),
                           "groups_straddling": straddle}


def check_class_floors(task: str, split: dict, ids: list[str], labels: list[str], min_test_support: int = 30):
    lab = dict(zip(ids, labels))
    classes = sorted(set(labels))
    floor = CLASS_FLOOR[task]
    shares, ok = {}, True
    for p in ("train", "val", "test"):
        c = Counter(lab[r] for r in split[p])
        for cls in classes:
            s = c[cls] / len(split[p])
            shares[f"{p}:{cls}"] = {"n": c[cls], "share": round(s, 4)}
            ok &= s >= floor
            if p == "test":
                ok &= c[cls] >= min_test_support
    return ok, {"floor": floor, "min_test_support": min_test_support, "shares": shares}


def check_id_not_predictive(ids: list[str], labels: list[str], max_auroc: float = 0.55):
    ordinal = np.asarray([int(re.search(r"(\d+)$", r).group(1)) for r in ids], dtype=np.float64)
    lab = np.asarray(labels)
    per = {}
    for cls in sorted(set(labels)):
        a = auroc_binary(ordinal, lab == cls)
        per[cls] = round(max(a, 1 - a), 4)
    worst = max(per.values())
    return worst <= max_auroc, {"max_one_vs_rest_auroc": worst, "per_class": per, "threshold": max_auroc}


def check_no_target_in_features(task: str, names: list[str], X: np.ndarray, T: np.ndarray, tnames: list[str],
                                max_corr: float = 0.999):
    bad_names = sorted(set(names) & OUTPUT_FIELDS[task])
    Xs = X.std(0)
    C = np.zeros((X.shape[1], T.shape[1]))
    for j in range(T.shape[1]):
        t = T[:, j]
        if t.std() > 0:
            for i in np.flatnonzero(Xs > 0):
                C[i, j] = np.corrcoef(X[:, i], t)[0, 1]
    flat = [(abs(C[i, j]), names[i] if i < len(names) else f"col{i}", tnames[j]) for i in range(C.shape[0]) for j in range(C.shape[1])]
    flat.sort(reverse=True)
    top = [{"feature": f, "target": t, "abs_corr": round(c, 4)} for c, f, t in flat[:10]]
    worst = flat[0][0] if flat else 0.0
    ok = not bad_names and worst < max_corr and len(names) == X.shape[1]
    return ok, {"feature_names_that_are_output_fields": bad_names, "max_abs_corr": round(worst, 5),
                "spec_names": len(names), "feature_columns": int(X.shape[1]), "top10": top}


def health(task: str, split: dict, ids: list[str], labels: list[str], X: np.ndarray, T: np.ndarray, tnames: list[str]):
    lab = dict(zip(ids, labels))
    pos = {r: i for i, r in enumerate(ids)}
    rep = {"rows": len(ids), "counts": {}}
    for p in ("train", "val", "test"):
        c = Counter(lab[r] for r in split[p])
        rep["counts"][p] = {"total": len(split[p]), **dict(sorted(c.items()))}
    corpus = Counter(labels)
    rep["imbalance"] = {"shares": {k: round(v / len(labels), 4) for k, v in sorted(corpus.items())},
                        "max_over_min_share": round(max(corpus.values()) / min(corpus.values()), 3)}
    _, cnt = np.unique(X, axis=0, return_counts=True)
    rep["exact_duplicate_feature_rows"] = int(cnt[cnt > 1].sum() - (cnt > 1).sum())
    rep["missing_values"] = int(np.isnan(X).sum())
    const = np.flatnonzero(X.std(0) < 1e-9)
    rep["constant_features"] = [int(i) for i in const]
    keep = np.flatnonzero(X.std(0) >= 1e-9)
    Xc = X[:, keep].astype(np.float64)
    R = np.corrcoef(Xc, rowvar=False)
    rank = int(np.linalg.matrix_rank(R, tol=1e-8))
    vif = np.diag(np.linalg.pinv(R))
    rep["multicollinearity"] = {"non_constant_features": int(len(keep)), "rank": rank,
                                "exactly_collinear_columns": int(len(keep) - rank),
                                "max_vif_pinv": round(float(np.max(vif)), 2),
                                "median_vif_pinv": round(float(np.median(vif)), 2)}
    tr = np.asarray([pos[r] for r in split["train"]]); te = np.asarray([pos[r] for r in split["test"]])
    rep["ks_train_vs_test"] = {n: round(float(ks_2samp(T[tr, j], T[te, j]).statistic), 4) for j, n in enumerate(tnames)}
    sd = T.std(0)
    rep["target_sd"] = {n: round(float(sd[j]), 4) for j, n in enumerate(tnames)}
    rep["degenerate_targets"] = [n for j, n in enumerate(tnames) if sd[j] < DEGENERATE_SD[task]]
    return rep


def run_task(task: str, split_path: Path, split: dict | None = None, X_override=None, names_override=None,
             labels_override=None, quiet=False) -> tuple[bool, dict]:
    ids, Xt, Y, labels = load_teacher(task, ROOT)
    X = Xt.numpy() if X_override is None else X_override
    labels = labels if labels_override is None else labels_override
    names = feature_names(task) if names_override is None else names_override
    T, tnames = targets_matrix(task, Y)
    split = split or json.loads(split_path.read_text())
    results = {
        "no_id_overlap": check_no_id_overlap(split, ids),
        "stratified": check_stratified(split, ids, labels),
        "no_duplicate_straddle": check_no_duplicate_straddle(split, ids, X),
        "class_floors": check_class_floors(task, split, ids, labels),
        "id_not_predictive": check_id_not_predictive(ids, labels),
        "no_target_in_features": check_no_target_in_features(task, names, X, T, tnames),
    }
    all_ok = all(ok for ok, _ in results.values())
    rep = {"task": task, "split_file": str(split_path.relative_to(ROOT)) if split_path.is_absolute() else str(split_path),
           "split_sha256": sha256_file(split_path) if split_path.exists() else None,
           "checks": {k: {"pass": ok, **d} for k, (ok, d) in results.items()},
           "health": health(task, split, ids, labels, X, T, tnames), "PASS": all_ok}
    if not quiet:
        for k, (ok, d) in results.items():
            short = {kk: vv for kk, vv in d.items() if kk not in ("top10", "shares", "per_class")}
            print(f"  [{'PASS' if ok else 'FAIL'}] {task}.{k}  {json.dumps(short)}")
    return all_ok, rep


def self_test() -> bool:
    """Plant faults; every one must be caught (rule: a verifier that passes its own red fixtures is broken)."""
    task = "dti"
    split_path = ROOT / "splits" / "dti_seed1.json"
    base = json.loads(split_path.read_text())
    ids, Xt, Y, labels = load_teacher(task, ROOT)
    reds = {}
    # 1. planted overlap: one test id copied into train
    s = json.loads(json.dumps(base)); s["train"].append(s["test"][0])
    ok, rep = run_task(task, split_path, split=s, quiet=True)
    reds["planted_overlap"] = not rep["checks"]["no_id_overlap"]["pass"]
    # 2. planted label column: composite/100 appended as a 66th feature (and named after an output field)
    X2 = np.concatenate([Xt.numpy(), Y["composite"].numpy()], 1)
    ok, rep = run_task(task, split_path, X_override=X2, names_override=feature_names(task) + ["composite"], quiet=True)
    c = rep["checks"]["no_target_in_features"]
    reds["planted_label_column"] = (not c["pass"]) and c["max_abs_corr"] >= 0.999 and "composite" in c["feature_names_that_are_output_fields"]
    # 3. planted id-range labelling (the original attested-baseline fault): label = tier by id ordinal
    ordered = sorted(set(labels)); n = len(labels)
    lab3 = [ordered[min(len(ordered) - 1, (5 * i) // n)] for i in range(n)]
    ok, rep = run_task(task, split_path, labels_override=lab3, quiet=True)
    reds["planted_id_range_labels"] = not rep["checks"]["id_not_predictive"]["pass"]
    # 4. planted straddle of a duplicate vector: copy row 0's features onto a row in another partition
    pos = {r: i for i, r in enumerate(ids)}
    X4 = Xt.numpy().copy(); X4[pos[base["test"][0]]] = X4[pos[base["train"][0]]]
    ok, rep = run_task(task, split_path, X_override=X4, quiet=True)
    reds["planted_duplicate_straddle"] = not rep["checks"]["no_duplicate_straddle"]["pass"]
    for k, caught in reds.items():
        print(f"  [{'RED as required' if caught else 'NOT CAUGHT'}] self-test {k}")
    return all(reds.values())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=1, help="which splits/{task}_seed{S}.json to check")
    ap.add_argument("--tasks", nargs="+", default=["dti", "bii"])
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--out", type=Path, default=ROOT / "splits" / "qa_report.json")
    a = ap.parse_args(argv)
    if a.self_test:
        ok = self_test()
        print("self-test:", "PASS (all planted faults caught)" if ok else "FAIL (a planted fault slipped through)")
        return 0 if ok else 1
    report, all_ok = {}, True
    for task in a.tasks:
        ok, rep = run_task(task, ROOT / "splits" / f"{task}_seed{a.seed}.json")
        h = rep["health"]
        print(f"  health {task}: dup rows {h['exact_duplicate_feature_rows']}, missing {h['missing_values']}, "
              f"constant features {h['constant_features']}, collinear cols {h['multicollinearity']['exactly_collinear_columns']}, "
              f"max VIF {h['multicollinearity']['max_vif_pinv']}, degenerate targets {h['degenerate_targets'] or 'none'}, "
              f"KS train/test {h['ks_train_vs_test']}")
        report[task] = rep
        all_ok &= ok
    report["PASS"] = all_ok
    a.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{'PASS' if all_ok else 'FAIL'}  -> {a.out.relative_to(ROOT)}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
