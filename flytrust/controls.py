"""Control arms with the same forward(x) -> heads interface as ConnectomeNet.

(a) degree_preserving_shuffle: Maslov-Sneppen edge swaps (a->b, c->d) => (a->d, c->b). Preserves every
    neuron's in- and out-degree and the edge count; each edge record (sign, synapse count) stays with its
    presynaptic neuron, so Dale's law still holds. Swaps producing self-loops or duplicate edges are rejected.
(b) erdos_renyi: uniform random directed graph, same N and E, no self-loops, no duplicates; per-neuron signs
    (Dale's law) are drawn and then flipped one neuron at a time until the excitatory EDGE fraction is within
    tolerance of the target (62.8% on the real graph). Synapse counts are a permutation of the real ones.
(c) MatchedMLP: F -> H -> H -> out, H solved so the trainable parameter count is within 2% of the target.
(d) RidgeReadout: closed-form ridge regression from raw features (torch.linalg.lstsq on the augmented system).
    Classification heads are fit as one-hot regression; the outputs are used directly as logits.
"""

from __future__ import annotations

import math

import numpy as np
import torch
import torch.nn as nn

from .graph import Graph
from .model import ConnectomeNet, OutputSpec, count_parameters


# ---------------------------------------------------------------- (a) shuffle
def degree_preserving_shuffle(graph: Graph, seed: int, swaps_per_edge: float = 1.0, max_rounds: int = 200) -> Graph:
    rng = np.random.default_rng(seed)
    n, e = graph.n, graph.e
    src = graph.src.copy()
    dst = graph.dst.copy()
    target = int(math.ceil(swaps_per_edge * e))
    accepted = 0
    keys = np.sort(src * n + dst)
    for _ in range(max_rounds):
        if accepted >= target:
            break
        perm = rng.permutation(e)
        half = e // 2
        i, j = perm[:half], perm[half:2 * half]              # disjoint edge pairs
        new_i = src[i] * n + dst[j]                           # a -> d
        new_j = src[j] * n + dst[i]                           # c -> b
        ok = (src[i] != dst[j]) & (src[j] != dst[i])          # no self-loops
        ok &= new_i != new_j
        # reject if the new edge already exists in the graph
        pos = np.searchsorted(keys, new_i); ok &= ~((pos < e) & (keys[np.minimum(pos, e - 1)] == new_i))
        pos = np.searchsorted(keys, new_j); ok &= ~((pos < e) & (keys[np.minimum(pos, e - 1)] == new_j))
        # reject collisions inside the batch: any new key proposed twice
        cand = np.concatenate([new_i[ok], new_j[ok]])
        uniq, cnt = np.unique(cand, return_counts=True)
        dup = uniq[cnt > 1]
        if len(dup):
            ok[ok] &= ~(np.isin(new_i[ok], dup) | np.isin(new_j[ok], dup))
        # cap so we do not overshoot the target too far
        idx = np.flatnonzero(ok)
        if len(idx) > target - accepted:
            idx = idx[: target - accepted]
        a, b = i[idx], j[idx]
        dst[a], dst[b] = dst[b].copy(), dst[a].copy()
        accepted += len(idx)
        keys = np.sort(src * n + dst)
    # sanity: sign/syn stay indexed by edge, so they still belong to src (unchanged)
    return Graph(n=n, src=src, dst=dst, sign=graph.sign.copy(), syn=graph.syn.copy(),
                 sensory_mask=graph.sensory_mask, descending_mask=graph.descending_mask,
                 motor_mask=graph.motor_mask, body_id=graph.body_id, superclass=graph.superclass,
                 meta=graph.meta, meta_sha256=graph.meta_sha256, name=f"{graph.name}-shuffle-s{seed}")


# ---------------------------------------------------------------- (b) ER
def erdos_renyi(graph: Graph, seed: int, exc_fraction: float | None = None, tol: float = 1e-3) -> Graph:
    rng = np.random.default_rng(seed)
    n, e = graph.n, graph.e
    if exc_fraction is None:
        exc_fraction = graph.excitatory_fraction
    keys = np.empty(0, dtype=np.int64)
    while len(keys) < e:
        need = e - len(keys)
        s = rng.integers(0, n, int(need * 1.05) + 16, dtype=np.int64)
        d = rng.integers(0, n, len(s), dtype=np.int64)
        k = (s * n + d)[s != d]
        keys = np.unique(np.concatenate([keys, k]))
    keys = rng.permutation(keys)[:e]
    src, dst = keys // n, keys % n
    # sort by src so the edge list is CSR-like as in the real graph
    order = np.lexsort((dst, src))
    src, dst = src[order], dst[order]
    outdeg = np.bincount(src, minlength=n)
    # per-neuron signs (Dale's law); flip neurons until the edge fraction matches
    neuron_sign = np.where(rng.random(n) < exc_fraction, 1, -1).astype(np.int8)
    for _ in range(100_000):
        frac = outdeg[neuron_sign > 0].sum() / e
        if abs(frac - exc_fraction) <= tol:
            break
        cand = np.flatnonzero((neuron_sign < 0) if frac < exc_fraction else (neuron_sign > 0))
        cand = cand[outdeg[cand] > 0]
        pick = rng.choice(cand)
        neuron_sign[pick] *= -1
    sign = neuron_sign[src]
    syn = rng.permutation(graph.syn)
    return Graph(n=n, src=src, dst=dst, sign=sign, syn=syn,
                 sensory_mask=graph.sensory_mask, descending_mask=graph.descending_mask,
                 motor_mask=graph.motor_mask, body_id=graph.body_id, superclass=graph.superclass,
                 meta=graph.meta, meta_sha256=graph.meta_sha256, name=f"{graph.name}-er-s{seed}")


# ---------------------------------------------------------------- (c) MLP
def solve_hidden_width(in_dim: int, out_dim: int, target: int, depth: int = 2) -> int:
    """Smallest H with params(H) >= target for F -> H -> ... (depth hidden layers) -> out. Exact for the
    quadratic when depth == 2; otherwise a bounded search."""
    def params(H):
        p = in_dim * H + H
        for _ in range(depth - 1):
            p += H * H + H
        return p + H * out_dim + out_dim
    lo, hi = 1, 1
    while params(hi) < target:
        hi *= 2
    while lo < hi:
        mid = (lo + hi) // 2
        if params(mid) >= target:
            hi = mid
        else:
            lo = mid + 1
    # pick whichever of lo-1 / lo is closer
    if lo > 1 and abs(params(lo - 1) - target) < abs(params(lo) - target):
        return lo - 1
    return lo


class MatchedMLP(nn.Module):
    arm = "mlp"

    def __init__(self, in_dim: int, spec: OutputSpec, target_params: int, depth: int = 2, tol: float = 0.02):
        super().__init__()
        self.spec, self.in_dim = spec, in_dim
        H = solve_hidden_width(in_dim, spec.total_dim, target_params, depth)
        layers, d = [], in_dim
        for _ in range(depth):
            layers += [nn.Linear(d, H), nn.ReLU()]
            d = H
        layers.append(nn.Linear(d, spec.total_dim))
        self.net = nn.Sequential(*layers)
        self.hidden_width = H
        got = count_parameters(self)
        if abs(got - target_params) / target_params > tol:
            raise ValueError(f"MatchedMLP has {got:,} params, target {target_params:,} (> {tol:.0%})")

    def forward(self, x):
        return self.spec.split(self.net(x))


# ---------------------------------------------------------------- (d) ridge
class RidgeReadout(nn.Module):
    arm = "ridge"

    def __init__(self, in_dim: int, spec: OutputSpec, lam: float = 1.0):
        super().__init__()
        self.spec, self.in_dim, self.lam = spec, in_dim, lam
        self.register_buffer("W", torch.zeros(in_dim + 1, spec.total_dim))   # last row = intercept

    def fit(self, X: torch.Tensor, Y: dict) -> "RidgeReadout":
        X = X.detach().cpu().double()
        cols = []
        for h in self.spec.heads:
            y = Y[h.name].detach().cpu()
            if h.kind == "classification":
                cols.append(torch.nn.functional.one_hot(y.long().reshape(-1), h.dim).double())
            else:
                cols.append(y.double().reshape(len(X), h.dim))
        T = torch.cat(cols, 1)
        Xa = torch.cat([X, torch.ones(len(X), 1, dtype=X.dtype)], 1)
        d = Xa.shape[1]
        reg = math.sqrt(self.lam) * torch.eye(d, dtype=X.dtype)
        reg[-1, -1] = 0.0                                            # do not shrink the intercept
        A = torch.cat([Xa, reg], 0)
        B = torch.cat([T, torch.zeros(d, T.shape[1], dtype=X.dtype)], 0)
        sol = torch.linalg.lstsq(A, B).solution
        self.W.copy_(sol.float().to(self.W.device))
        return self

    def forward(self, x):
        xa = torch.cat([x, torch.ones(len(x), 1, device=x.device, dtype=x.dtype)], 1)
        return self.spec.split(xa @ self.W)


# ---------------------------------------------------------------- dispatch
ARMS = ("connectome", "shuffle", "er", "mlp", "ridge")


def build_arm(arm: str, graph: Graph, in_dim: int, spec: OutputSpec, T: int, device, seed: int, **kw):
    """Return (model, meta). Controls (b)/(a) are ConnectomeNets on a surrogate graph."""
    meta = {"arm": arm, "graph": graph.summary()}
    if arm == "connectome":
        m = ConnectomeNet(graph, in_dim, spec, T=T, device=device, **kw)
    elif arm == "shuffle":
        g = degree_preserving_shuffle(graph, seed=seed, swaps_per_edge=kw.pop("swaps_per_edge", 1.0))
        meta["graph"] = g.summary()
        m = ConnectomeNet(g, in_dim, spec, T=T, device=device, **kw)
    elif arm == "er":
        g = erdos_renyi(graph, seed=seed)
        meta["graph"] = g.summary()
        m = ConnectomeNet(g, in_dim, spec, T=T, device=device, **kw)
    elif arm == "mlp":
        ref = ConnectomeNet(graph, in_dim, spec, T=T, device="cpu")
        target = count_parameters(ref)
        del ref
        torch.manual_seed(seed)
        m = MatchedMLP(in_dim, spec, target).to(device)
        meta["target_params"] = target
        meta["hidden_width"] = m.hidden_width
    elif arm == "ridge":
        m = RidgeReadout(in_dim, spec, lam=kw.get("lam", 1.0)).to(device)
    else:
        raise ValueError(f"unknown arm {arm!r}; choose from {ARMS}")
    meta["trainable_params"] = count_parameters(m)
    return m, meta
