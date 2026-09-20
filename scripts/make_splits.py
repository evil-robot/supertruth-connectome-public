"""Deterministic train/val/test splits for the two teacher corpora.

Scheme (PROTOCOL.md section 4.1, applied to the teacher files as generated):
  * fractions 70/10/20 (the protocol fixes these; the pilot brief's 70/15/15 yields to the protocol);
  * stratified on the teacher label: DTI tier (5 classes), BII gate (4 classes); per class, rows are shuffled
    once and cut at round(0.7 n_c) / round(0.1 n_c) / rest;
  * the unit is a GROUP = the set of rows with an identical feature vector (a group's stratum is its modal
    label). The protocol groups by base_id (DTI) and agent_id (BII); the teacher files carry neither (every row
    is an independent draw, teachers/MANIFEST.md), so identical inputs are the only near-duplicates that exist:
    DTI has 20,000 distinct vectors (group = record); BII has 19,994 (one group of 7 all-zero windows);
  * ONE fixed partition per corpus, RNG seed 20260920 (protocol: "the fixed split is the same for every arm so
    comparisons are paired"). It is written once per run seed S as splits/{task}_seed{S}.json so a run can
    carry its own split file; the partitions inside those files are identical by construction.

  .venv/bin/python scripts/make_splits.py [--seeds 1 2 3 4 5] [--split-seed 20260920]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flytrust.data_adapters import load_teacher, TEACHER_FILE, MANIFEST_SHA256, LABEL_FIELD   # noqa: E402
from flytrust.graph import ROOT, sha256_file                                                  # noqa: E402

FRACTIONS = {"train": 0.7, "val": 0.1, "test": 0.2}
SPLIT_SEED = 20260920


def stratified_partition(X: np.ndarray, labels: list[str], seed: int) -> dict:
    """Group-aware stratified split. Groups = identical feature vectors; never straddle. Per class (group modal
    label) the groups are shuffled once and assigned to train until >= 70% of the class's ROWS, then val until
    >= 10%, rest test."""
    rng = np.random.default_rng(seed)
    labels = np.asarray(labels)
    _, ginv = np.unique(X, axis=0, return_inverse=True)
    ginv = ginv.ravel()
    n_groups = ginv.max() + 1
    members = [[] for _ in range(n_groups)]
    for i, g in enumerate(ginv):
        members[g].append(i)
    modal = np.empty(n_groups, dtype=object)
    for g, rows in enumerate(members):
        vals, cnt = np.unique(labels[rows], return_counts=True)
        modal[g] = vals[cnt.argmax()]
    out = {"train": [], "val": [], "test": []}
    for cls in sorted(set(labels.tolist())):
        groups = np.flatnonzero(modal == cls)
        groups = groups[rng.permutation(len(groups))]
        n_rows = sum(len(members[g]) for g in groups)
        cut_tr = int(round(FRACTIONS["train"] * n_rows))
        cut_va = cut_tr + int(round(FRACTIONS["val"] * n_rows))
        seen = 0
        for g in groups:
            part = "train" if seen < cut_tr else ("val" if seen < cut_va else "test")
            out[part].extend(members[g])
            seen += len(members[g])
    return {k: np.sort(np.asarray(v, dtype=np.int64)) for k, v in out.items()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    ap.add_argument("--split-seed", type=int, default=SPLIT_SEED)
    ap.add_argument("--tasks", nargs="+", default=["dti", "bii"])
    ap.add_argument("--out", type=Path, default=ROOT / "splits")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)

    for task in a.tasks:
        path = ROOT / TEACHER_FILE[task]
        sha = sha256_file(path)
        if sha != MANIFEST_SHA256[task]:
            raise SystemExit(f"{path}: sha256 {sha} != MANIFEST {MANIFEST_SHA256[task]}")
        ids, X, Y, labels = load_teacher(task, ROOT)
        parts = stratified_partition(X.numpy(), labels, a.split_seed)
        counts = {p: dict(sorted(Counter(labels[i] for i in idx).items())) for p, idx in parts.items()}
        for S in a.seeds:
            doc = {
                "task": task, "run_seed": S, "split_seed": a.split_seed,
                "scheme": "group-aware stratified shuffle split, group = identical feature vector, stratum = group modal "
                          "label; one fixed partition per corpus (protocol 4.1), identical across run seeds",
                "fractions": FRACTIONS, "stratify_on": LABEL_FIELD[task], "n": len(ids),
                "teacher_file": TEACHER_FILE[task], "teacher_sha256": sha, "teacher_sha256_manifest": MANIFEST_SHA256[task],
                "counts": {p: {"total": int(len(parts[p])), **counts[p]} for p in parts},
                "train": [ids[i] for i in parts["train"]],
                "val": [ids[i] for i in parts["val"]],
                "test": [ids[i] for i in parts["test"]],
            }
            out = a.out / f"{task}_seed{S}.json"
            out.write_text(json.dumps(doc, indent=None, separators=(",", ":")) + "\n")
            print(f"{out.relative_to(ROOT)}  sha256 {sha256_file(out)[:16]}  "
                  f"{ {p: len(parts[p]) for p in parts} }")
        print(f"  {task} per-class counts: {json.dumps(counts)}")


if __name__ == "__main__":
    main()
