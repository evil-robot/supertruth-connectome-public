"""Rule 13: the share of readout neurons reachable from the sensory set within T directed hops.

  .venv/bin/python scripts/reachability.py [--T 8] [--out results/reachability.json]

Breadth-first search over the threshold-5 CSR (data/malecns/graph.npz, presynaptic row -> postsynaptic column) from
every sensory neuron at once. dist[i] is the fewest directed edges from any sensory neuron to neuron i (0 for the
sensory set itself, -1 when no path exists). Two shares are written for the readout set (descending + motor) and for
all neurons: within T hops (dist <= T, the wording of DECISION_RULES rule 13) and within T - 1 hops, which is what the
synchronous update actually delivers: h_0 = 0 and the sensory drive enters at step 1, so a neuron d hops away first
carries input at step d + 1 and the readout taken after step T sees input from neurons with dist <= T - 1
(flytrust/model.py, forward). Nothing here is estimated; every number is a count on the graph as built.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import numpy as np
import scipy.sparse as sp

ROOT = Path(__file__).resolve().parents[1]
NPZ = ROOT / "data" / "malecns" / "graph.npz"
META = ROOT / "data" / "malecns" / "graph_meta.json"
OUT = ROOT / "results" / "reachability.json"

# role sets as flytrust/graph.py defines them
SENSORY_SC = {"ol_sensory", "cb_sensory", "vnc_sensory", "sensory_ascending", "sensory_descending",
              "cb_sensory_tbc", "vnc_sensory_tbc", "sensory_ascending_tbc"}
DESCENDING_SC = {"descending_neuron", "descending_neuron_tbc"}
MOTOR_SC = {"vnc_motor", "cb_motor"}


def bfs_distances(adj: sp.csr_matrix, sources: np.ndarray) -> np.ndarray:
    """fewest directed hops from the source set to every node; -1 where unreachable"""
    n = adj.shape[0]
    dist = np.full(n, -1, dtype=np.int32)
    dist[sources] = 0
    frontier = np.zeros(n, dtype=np.float32)
    frontier[sources] = 1.0
    hop = 0
    while True:
        hop += 1
        reached = adj.T.dot(frontier) > 0            # post-synaptic partners of the frontier
        new = reached & (dist < 0)
        if not new.any():
            return dist
        dist[new] = hop
        frontier = new.astype(np.float32)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--T", type=int, default=8, help="synchronous steps in the model (PROTOCOL A5)")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    T = a.T

    z = np.load(NPZ, allow_pickle=False)
    indptr = z["indptr"].astype(np.int64)
    indices = z["indices"].astype(np.int64)
    n = len(indptr) - 1
    e = len(indices)
    adj = sp.csr_matrix((np.ones(e, dtype=np.float32), indices, indptr), shape=(n, n))
    sc = z["superclass"]
    sensory = np.isin(sc, list(SENSORY_SC))
    readout = np.isin(sc, list(DESCENDING_SC)) | np.isin(sc, list(MOTOR_SC))

    dist = bfs_distances(adj, np.flatnonzero(sensory))
    max_hop = int(dist.max())

    def cumulative(mask: np.ndarray) -> dict:
        d = dist[mask]
        total = int(mask.sum())
        by_hop = {str(h): int((d == h).sum()) for h in range(max_hop + 1)}
        by_hop["unreachable"] = int((d < 0).sum())
        within = {str(h): int(((d >= 0) & (d <= h)).sum()) for h in range(max(max_hop, T) + 1)}
        finite = d[d >= 0]
        return {"n": total, "count_at_hop": by_hop, "count_within_hops": within,
                "share_within_hops": {h: c / total for h, c in within.items()},
                "share_within_T": within[str(T)] / total,
                "share_within_T_minus_1": within[str(T - 1)] / total,
                "share_unreachable": by_hop["unreachable"] / total,
                "median_hops_reachable": float(np.median(finite)) if len(finite) else None,
                "mean_hops_reachable": float(finite.mean()) if len(finite) else None,
                "max_hops_reachable": int(finite.max()) if len(finite) else None}

    non_sensory = ~sensory
    out = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "script": "scripts/reachability.py",
        "graph": {"npz": NPZ.relative_to(ROOT).as_posix(), "graph_meta_sha256": hashlib.sha256(META.read_bytes()).hexdigest(),
                  "n_neurons": n, "n_edges": e, "threshold": int(z["threshold"])},
        "T": T,
        "hop_convention": ("dist = fewest directed edges from any sensory neuron; within T means dist <= T (rule 13 wording); "
                           "the synchronous update delivers sensory input to a neuron d hops away at step d + 1, so the readout "
                           "after T steps carries input from neurons with dist <= T - 1 (flytrust/model.py)"),
        "sets": {"n_sensory": int(sensory.sum()), "n_readout": int(readout.sum()),
                 "n_descending": int(np.isin(sc, list(DESCENDING_SC)).sum()), "n_motor": int(np.isin(sc, list(MOTOR_SC)).sum()),
                 "sensory_and_readout_overlap": int((sensory & readout).sum())},
        "readout": cumulative(readout),
        "all_neurons": cumulative(np.ones(n, dtype=bool)),
        "non_sensory_neurons": cumulative(non_sensory),
        "rule_13": {"floor": 0.90, "share_within_T": None, "passes": None},
    }
    out["rule_13"]["share_within_T"] = out["readout"]["share_within_T"]
    out["rule_13"]["passes"] = out["readout"]["share_within_T"] >= 0.90
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=2) + "\n")

    r, al = out["readout"], out["all_neurons"]
    print(f"N = {n:,}, E = {e:,}, sensory {out['sets']['n_sensory']:,}, readout {out['sets']['n_readout']:,}, T = {T}")
    print(f"readout within {T} hops: {r['count_within_hops'][str(T)]:,} of {r['n']:,} = {r['share_within_T']:.4f}; "
          f"within {T - 1}: {r['share_within_T_minus_1']:.4f}; unreachable {r['count_at_hop']['unreachable']:,}; "
          f"median hops {r['median_hops_reachable']}, max {r['max_hops_reachable']}")
    print(f"all neurons within {T} hops: {al['count_within_hops'][str(T)]:,} of {al['n']:,} = {al['share_within_T']:.4f}; "
          f"unreachable {al['count_at_hop']['unreachable']:,}; max finite distance {max_hop}")
    print(f"rule 13 (floor 0.90): {'PASS' if out['rule_13']['passes'] else 'FAIL'}; wrote {a.out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
