"""Datasets for the trainer: (X float32 [N,F], Y dict of per-head targets) plus index splits from a file.

Regression targets are stored SCALED TO 0-1 (the trainer reports MAE x100). Classification targets are int64
class indices in the order given by the OutputSpec (model.TIERS / model.GATES).

Teacher loaders (load_dti_teacher_jsonl / load_bii_teacher_jsonl) read teachers/*.jsonl:
  dti_teacher.jsonl  one record per line:
      features   -> X row (65 floats, teachers/dti_features_spec.md)
      dimensions -> Y["dims"]      = [provenance..stability] / 100        (shape [N,8])
      composite  -> Y["composite"] = composite / 100                       (shape [N,1])
      tier       -> Y["tier"]      = index into model.TIERS
  bii_teacher.jsonl
      features   -> X row (58 floats, teachers/bii_features_spec.md)
      bii        -> Y["bii"]  (shape [N,1])
      gate       -> Y["gate"] = index into model.GATES (file is lower case; matched case-insensitively)
Standardizer fits on the TRAIN index set only (it refuses any other partition tag) and is saved per run.
Splits come from splits/{task}_seed{S}.json (scripts/make_splits.py); load_split_json maps ids to rows.
Until then, accept a .npz with keys X, Y_<head> (see load_npz_dataset) and splits.npz with train_idx, val_idx.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from .model import OutputSpec, DTI_SPEC, BII_SPEC


def load_npz_dataset(path: Path, spec: OutputSpec):
    z = np.load(path, allow_pickle=False)
    X = torch.from_numpy(z["X"].astype(np.float32))
    Y = {}
    for h in spec.heads:
        key = f"Y_{h.name}"
        if key not in z.files:
            raise KeyError(f"{path}: missing {key}; have {z.files}")
        arr = z[key]
        if h.kind == "regression":
            t = torch.from_numpy(arr.astype(np.float32)).reshape(len(X), h.dim)
            if t.min() < -1e-6 or t.max() > 1 + 1e-6:
                raise ValueError(f"{key} must be scaled to 0-1 (got [{t.min():.3f}, {t.max():.3f}])")
        else:
            t = torch.from_numpy(arr.astype(np.int64)).reshape(len(X))
            if t.min() < 0 or t.max() >= h.dim:
                raise ValueError(f"{key} has class index outside 0..{h.dim - 1}")
        Y[h.name] = t
    return X, Y


def save_npz_dataset(path: Path, X: torch.Tensor, Y: dict):
    np.savez(path, X=X.numpy().astype(np.float32), **{f"Y_{k}": v.numpy() for k, v in Y.items()})


def load_splits(path: Path):
    """Splits are never made inside the trainer; they come from this file (npz with train_idx, val_idx)."""
    z = np.load(path, allow_pickle=False)
    tr, va = z["train_idx"].astype(np.int64), z["val_idx"].astype(np.int64)
    if len(np.intersect1d(tr, va)):
        raise ValueError("train and val indices overlap")
    return tr, va


def make_splits(path: Path, n: int, val_fraction: float, seed: int):
    rng = np.random.default_rng(seed)
    perm = rng.permutation(n)
    n_val = int(round(val_fraction * n))
    np.savez(path, train_idx=np.sort(perm[n_val:]), val_idx=np.sort(perm[:n_val]))
    return load_splits(path)


DTI_DIMS = ["provenance", "consent", "recency", "quality", "concordance", "validation", "breadth", "stability"]
DTI_WEIGHTS = [25, 20, 15, 10, 10, 10, 5, 5]      # pipeline.ts defaults, same order as DTI_DIMS
FEATURE_LEN = {"dti": 65, "bii": 58}
TEACHER_N = 20_000
TEACHER_FILE = {"dti": "teachers/dti_teacher.jsonl", "bii": "teachers/bii_teacher.jsonl"}
ID_FIELD = {"dti": "record_id", "bii": "window_id"}
LABEL_FIELD = {"dti": "tier", "bii": "gate"}
# sha256 of the teacher files as recorded in teachers/MANIFEST.md (verified against the file by the callers)
MANIFEST_SHA256 = {
    "dti": "2aa26f37b1be93f7af42c4eebfb8f8b03a92839fc433d0e11a0df928936c4b22",
    "bii": "c43bb314823f19f35bd993d9860bd444663137bae48c4c836826e7cd7372f67b",
}


def _iter_jsonl(path: Path):
    import json
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def load_dti_teacher_jsonl(path: Path, feature_len: int = FEATURE_LEN["dti"], n_expected: int = TEACHER_N):
    """Returns (ids, X float32 [N,65], Y dict, labels list[str]). Asserts spec length on every row and N."""
    from .model import TIERS
    ids, feats, dims, comp, tier = [], [], [], [], []
    for r in _iter_jsonl(path):
        f = r["features"]
        if len(f) != feature_len:
            raise ValueError(f"{r.get('record_id')}: {len(f)} features, spec says {feature_len}")
        ids.append(r["record_id"])
        feats.append(f)
        dims.append([r["dimensions"][d] for d in DTI_DIMS])
        comp.append(r["composite"])
        tier.append(TIERS.index(r["tier"]))
    if len(ids) != n_expected:
        raise ValueError(f"{path}: {len(ids)} rows, expected {n_expected}")
    X = torch.from_numpy(np.asarray(feats, dtype=np.float32))
    Y = {"dims": torch.from_numpy(np.asarray(dims, dtype=np.float32) / 100.0),
         "composite": torch.from_numpy(np.asarray(comp, dtype=np.float32) / 100.0).reshape(-1, 1),
         "tier": torch.from_numpy(np.asarray(tier, dtype=np.int64))}
    _check_targets(X, Y, DTI_SPEC)
    return ids, X, Y, [TIERS[t] for t in tier]


def load_bii_teacher_jsonl(path: Path, feature_len: int = FEATURE_LEN["bii"], n_expected: int = TEACHER_N):
    """Returns (ids, X float32 [N,58], Y dict, labels list[str])."""
    from .model import GATES
    ids, feats, bii, gate = [], [], [], []
    for r in _iter_jsonl(path):
        f = r["features"]
        if len(f) != feature_len:
            raise ValueError(f"{r.get('window_id')}: {len(f)} features, spec says {feature_len}")
        ids.append(r["window_id"])
        feats.append(f)
        bii.append(r["bii"])
        gate.append(GATES.index(str(r["gate"]).upper()))
    if len(ids) != n_expected:
        raise ValueError(f"{path}: {len(ids)} rows, expected {n_expected}")
    X = torch.from_numpy(np.asarray(feats, dtype=np.float32))
    Y = {"bii": torch.from_numpy(np.asarray(bii, dtype=np.float32)).reshape(-1, 1),
         "gate": torch.from_numpy(np.asarray(gate, dtype=np.int64))}
    _check_targets(X, Y, BII_SPEC)
    return ids, X, Y, [GATES[g] for g in gate]


def _check_targets(X, Y, spec):
    if not torch.isfinite(X).all():
        raise ValueError("non-finite feature value")
    for h in spec.heads:
        t = Y[h.name]
        if h.kind == "regression":
            if t.shape != (len(X), h.dim) or t.min() < 0 or t.max() > 1:
                raise ValueError(f"{h.name}: shape {tuple(t.shape)} range [{t.min():.3f},{t.max():.3f}]")
        elif t.shape != (len(X),) or t.min() < 0 or t.max() >= h.dim:
            raise ValueError(f"{h.name}: bad class indices")


def load_teacher(task: str, root: Path):
    path = Path(root) / TEACHER_FILE[task]
    return (load_dti_teacher_jsonl if task == "dti" else load_bii_teacher_jsonl)(path)


class Standardizer:
    """Per-feature z-scoring. fit() accepts only partition="train" (protocol rule 7); constant columns get std 1."""

    def __init__(self, mean: np.ndarray, std: np.ndarray, n_fit: int, partition: str):
        self.mean, self.std, self.n_fit, self.partition = mean.astype(np.float32), std.astype(np.float32), int(n_fit), partition

    @classmethod
    def fit(cls, X: torch.Tensor, idx: np.ndarray, partition: str = "train") -> "Standardizer":
        if partition != "train":
            raise ValueError(f"Standardizer may only be fit on the train partition, got {partition!r}")
        sub = X[torch.as_tensor(np.asarray(idx), dtype=torch.long)].numpy().astype(np.float64)
        mean = sub.mean(0)
        std = sub.std(0)
        std = np.where(std < 1e-6, 1.0, std)
        return cls(mean, std, len(idx), partition)

    def transform(self, X: torch.Tensor) -> torch.Tensor:
        return (X - torch.from_numpy(self.mean)) / torch.from_numpy(self.std)

    def to_dict(self) -> dict:
        return {"partition": self.partition, "n_fit": self.n_fit,
                "mean": self.mean.tolist(), "std": self.std.tolist()}

    def save(self, path: Path):
        import json
        Path(path).write_text(json.dumps(self.to_dict()) + "\n")

    @classmethod
    def load(cls, path: Path) -> "Standardizer":
        import json
        d = json.loads(Path(path).read_text())
        return cls(np.asarray(d["mean"]), np.asarray(d["std"]), d["n_fit"], d["partition"])


def load_split_json(path: Path, ids: list) -> dict:
    """Split file -> {"train": idx, "val": idx, "test": idx, "meta": {...}}; ids must cover every listed id
    exactly once and the three partitions must be disjoint."""
    import json
    d = json.loads(Path(path).read_text())
    pos = {rid: i for i, rid in enumerate(ids)}
    if len(pos) != len(ids):
        raise ValueError("duplicate ids in the teacher file")
    out, seen = {}, set()
    for part in ("train", "val", "test"):
        part_ids = d[part]
        if seen.intersection(part_ids):
            raise ValueError(f"split {path}: ids overlap between partitions")
        seen.update(part_ids)
        out[part] = np.asarray([pos[r] for r in part_ids], dtype=np.int64)
    out["meta"] = {k: v for k, v in d.items() if k not in ("train", "val", "test")}
    return out


def synthetic_dataset(n: int, in_dim: int, spec: OutputSpec, seed: int):
    """Smoke-test targets: a FIXED random linear + nonlinear function of X, with class heads as quantile bins
    of the first regression head's mean. Deterministic in (n, in_dim, spec, seed)."""
    g = torch.Generator().manual_seed(seed)
    X = torch.randn(n, in_dim, generator=g)
    Y = {}
    reg_heads = [h for h in spec.heads if h.kind == "regression"]
    cls_heads = [h for h in spec.heads if h.kind == "classification"]
    base = None
    for h in reg_heads:
        A = torch.randn(in_dim, h.dim, generator=g) / in_dim ** 0.5
        B = torch.randn(in_dim, h.dim, generator=g) / in_dim ** 0.5
        C = torch.randn(in_dim, h.dim, generator=g) / in_dim ** 0.5
        z = X @ A + 0.7 * torch.sin(2.0 * (X @ B)) + 0.5 * torch.tanh(X @ C) ** 2
        y = torch.sigmoid(1.5 * z)
        if base is None:
            base = y.mean(1)
        elif h.dim == 1:
            y = base[:, None] + 0.05 * (y - 0.5)   # a composite-like head tied to the first head
            y = y.clamp(0, 1)
        Y[h.name] = y
    for h in cls_heads:
        qs = torch.quantile(base, torch.linspace(0, 1, h.dim + 1)[1:-1])
        Y[h.name] = torch.bucketize(base, qs)
    return X, Y


SPEC_BY_NAME = {"dti": DTI_SPEC, "bii": BII_SPEC}
