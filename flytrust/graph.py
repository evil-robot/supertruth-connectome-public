"""Load data/malecns/graph.npz into an edge-list Graph.

graph.npz is CSR, presynaptic (row) -> postsynaptic (column); see data/README.md for the key table.
The Graph here is the expanded edge list (src, dst, sign, syn) plus role masks. Nothing in data/ is written.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NPZ = ROOT / "data" / "malecns" / "graph.npz"
DEFAULT_META = ROOT / "data" / "malecns" / "graph_meta.json"

# Superclass sets from data/README.md / data/build_graph.py.
SENSORY_SC = {"ol_sensory", "cb_sensory", "vnc_sensory", "sensory_ascending", "sensory_descending",
              "cb_sensory_tbc", "vnc_sensory_tbc", "sensory_ascending_tbc"}
DESCENDING_SC = {"descending_neuron", "descending_neuron_tbc"}
MOTOR_SC = {"vnc_motor", "cb_motor"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Graph:
    n: int
    src: np.ndarray            # int64 [E] presynaptic index
    dst: np.ndarray            # int64 [E] postsynaptic index
    sign: np.ndarray           # int8  [E] +1 / -1 (fixed, from edge_sign)
    syn: np.ndarray            # int32 [E] synapse count
    sensory_mask: np.ndarray   # bool [N]
    descending_mask: np.ndarray
    motor_mask: np.ndarray
    body_id: np.ndarray = None          # int64 [N]
    superclass: np.ndarray = None       # str [N]
    meta: dict = field(default_factory=dict)
    meta_sha256: str = ""
    name: str = "malecns"

    # ---- construction -------------------------------------------------
    @classmethod
    def from_edges(cls, n, src, dst, sign, syn, sensory_mask, descending_mask, motor_mask, **kw) -> "Graph":
        src = np.asarray(src, dtype=np.int64)
        dst = np.asarray(dst, dtype=np.int64)
        sign = np.asarray(sign, dtype=np.int8)
        syn = np.asarray(syn, dtype=np.int32)
        e = len(src)
        if not (len(dst) == len(sign) == len(syn) == e):
            raise ValueError("edge arrays differ in length")
        if e and (src.min() < 0 or dst.min() < 0 or src.max() >= n or dst.max() >= n):
            raise ValueError("edge index out of range")
        for m in (sensory_mask, descending_mask, motor_mask):
            if m.shape != (n,) or m.dtype != np.bool_:
                raise ValueError("role masks must be bool [N]")
        if kw.get("body_id") is None:
            kw["body_id"] = np.arange(n, dtype=np.int64)
        if kw.get("superclass") is None:
            kw["superclass"] = np.full(n, "", dtype="<U1")
        return cls(n=n, src=src, dst=dst, sign=sign, syn=syn, sensory_mask=np.asarray(sensory_mask),
                   descending_mask=np.asarray(descending_mask), motor_mask=np.asarray(motor_mask), **kw)

    # ---- derived -----------------------------------------------------
    @property
    def e(self) -> int:
        return len(self.src)

    def out_degree(self) -> np.ndarray:
        return np.bincount(self.src, minlength=self.n)

    def in_degree(self) -> np.ndarray:
        return np.bincount(self.dst, minlength=self.n)

    def gain_init(self) -> np.ndarray:
        """log1p(synapse count) per edge, float32: the initial gain magnitude."""
        return np.log1p(self.syn.astype(np.float32)).astype(np.float32)

    @property
    def readout_mask(self) -> np.ndarray:
        return self.descending_mask | self.motor_mask

    @property
    def excitatory_fraction(self) -> float:
        return float((self.sign > 0).mean()) if self.e else float("nan")

    def summary(self) -> dict:
        return {"name": self.name, "n": int(self.n), "e": int(self.e),
                "n_sensory": int(self.sensory_mask.sum()), "n_descending": int(self.descending_mask.sum()),
                "n_motor": int(self.motor_mask.sum()), "excitatory_fraction": self.excitatory_fraction,
                "meta_sha256": self.meta_sha256}

    # ---- subgraph ----------------------------------------------------
    def subgraph(self, k_neurons: int, seed: int = 0) -> "Graph":
        """Smoke-test graph: the k highest-degree neurons plus induced edges.

        So the model still has inputs and a readout, the k slots are filled as: the top ~10% of k by degree
        among sensory neurons, the top ~5% of k among descending+motor, and the rest from all remaining
        neurons by degree. Ties in degree are broken by a seeded random permutation.
        """
        if k_neurons >= self.n:
            return self
        rng = np.random.default_rng(seed)
        deg = (self.in_degree() + self.out_degree()).astype(np.float64)
        jitter = rng.random(self.n) * 0.5           # < 1, so only ties are reordered
        score = deg + jitter
        k_sens = max(1, int(round(0.10 * k_neurons)))
        k_ro = max(1, int(round(0.05 * k_neurons)))

        def top(mask, k):
            idx = np.flatnonzero(mask)
            idx = idx[np.argsort(-score[idx], kind="stable")]
            return idx[:k]

        keep = np.zeros(self.n, dtype=bool)
        keep[top(self.sensory_mask, k_sens)] = True
        keep[top(self.readout_mask & ~keep, k_ro)] = True
        rest = k_neurons - int(keep.sum())
        keep[top(~keep, rest)] = True
        return self.induced(np.flatnonzero(keep), name=f"{self.name}-sub{k_neurons}-s{seed}")

    def induced(self, nodes: np.ndarray, name: str | None = None) -> "Graph":
        nodes = np.sort(np.asarray(nodes, dtype=np.int64))
        remap = np.full(self.n, -1, dtype=np.int64)
        remap[nodes] = np.arange(len(nodes))
        keep_e = (remap[self.src] >= 0) & (remap[self.dst] >= 0)
        return Graph(n=len(nodes), src=remap[self.src[keep_e]], dst=remap[self.dst[keep_e]],
                     sign=self.sign[keep_e], syn=self.syn[keep_e],
                     sensory_mask=self.sensory_mask[nodes], descending_mask=self.descending_mask[nodes],
                     motor_mask=self.motor_mask[nodes], body_id=self.body_id[nodes],
                     superclass=self.superclass[nodes], meta=self.meta, meta_sha256=self.meta_sha256,
                     name=name or f"{self.name}-induced{len(nodes)}")


def load_graph(npz_path: Path = DEFAULT_NPZ, meta_path: Path = DEFAULT_META) -> Graph:
    z = np.load(npz_path, allow_pickle=False)
    indptr = z["indptr"].astype(np.int64)
    n = len(indptr) - 1
    src = np.repeat(np.arange(n, dtype=np.int64), np.diff(indptr))
    dst = z["indices"].astype(np.int64)
    sign = z["edge_sign"].astype(np.int8)
    syn = z["syn_count"].astype(np.int32)
    sc = z["superclass"]
    meta = json.loads(Path(meta_path).read_text()) if Path(meta_path).is_file() else {}
    meta_sha = sha256_file(Path(meta_path)) if Path(meta_path).is_file() else ""
    return Graph.from_edges(
        n=n, src=src, dst=dst, sign=sign, syn=syn,
        sensory_mask=np.isin(sc, list(SENSORY_SC)), descending_mask=np.isin(sc, list(DESCENDING_SC)),
        motor_mask=np.isin(sc, list(MOTOR_SC)), body_id=z["body_id"].astype(np.int64), superclass=sc,
        meta=meta, meta_sha256=meta_sha, name="malecns")
