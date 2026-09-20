"""Precompute the compact binaries behind viz/connectome.html.

Inputs
  data/malecns/graph.npz, graph_meta.json                  neuron order (sorted body_id), roles, NT class, signed CSR
  data/malecns/body-annotations-...feather                 somaLocation / tosomaLocation (8 nm voxels)
  data/malecns/synapse_centroids.npz                       per-neuron synapse centroid (8 nm voxels), from
                                                           viz/fetch_synapse_centroids.py (fallback position)
Outputs (viz/)
  points.bin            Float32 xyz [N,3] in micrometres (8 nm voxels x 0.008), then Uint8 role [N],
                        Uint8 nt_class [N], Uint8 pos_source [N]
  activity_frames.bin   Uint8 [T=8, N] activity per step, 255 * sqrt(h / act_max), 0 only where h == 0 (see points_meta.json)
  sample40k.bin         Uint32 [40000] stratified sample indices (by role, proportional, small roles kept whole)
  points_meta.json      counts, byte offsets, scaling, provenance

Roles: 0 other, 1 sensory input, 2 descending, 3 motor.   NT class: 0 excitatory, 1 inhibitory, 2 modulatory, 3 unclear.
Position source: 0 somaLocation, 1 tosomaLocation, 2 synapse centroid, 3 none (placed at NaN, dropped by the page).

Activity frames: forward pass of the frozen signed graph with UNIT gains and a RANDOM sensory input (seed 0),
the placeholder until the trained run drops in (same file layout). Per step, with the model's leak a = 0.5:
  agg_i = sum_{e: dst=i} sign_e * h[src_e]           unit gain per edge
  pre_i = agg_i / in_degree_i  (+ drive_i if sensory)
  h     = 0.5 h + 0.5 relu(pre)
This mirrors flytrust/model.py at init with g_e = 1 and norm = 1 / total incoming gain (= in-degree here).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pyarrow.feather as feather
import scipy.sparse as sp

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "malecns"
VIZ = ROOT / "viz"
ANNOT = DATA / "body-annotations-male-cns-v1.0-minconf-0.5.feather"
CENTROIDS = DATA / "synapse_centroids.npz"
VOXEL_UM = 0.008          # MaleCNS EM space is 8 nm isotropic (male-cns.janelia.org/download)
T = 8
SEED = 0
SAMPLE_N = 40_000

SENSORY_SC = {"ol_sensory", "cb_sensory", "vnc_sensory", "sensory_ascending", "sensory_descending",
              "cb_sensory_tbc", "vnc_sensory_tbc", "sensory_ascending_tbc"}
DESCENDING_SC = {"descending_neuron", "descending_neuron_tbc"}
MOTOR_SC = {"vnc_motor", "cb_motor"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def positions(ids: np.ndarray):
    """xyz in 8 nm voxels [N,3] float64 (NaN where unknown) and source code [N] uint8."""
    n = len(ids)
    ann = feather.read_table(ANNOT, columns=["bodyId", "somaLocation", "tosomaLocation"]).to_pandas()
    ann = ann.set_index("bodyId").reindex(ids)
    xyz = np.full((n, 3), np.nan)
    src = np.full(n, 3, dtype=np.uint8)
    for code, col in ((1, "tosomaLocation"), (0, "somaLocation")):     # soma wins where both exist
        has = ann[col].notna().to_numpy()
        if has.any():
            xyz[has] = np.stack(ann.loc[has, col].to_numpy()).astype(np.float64)
            src[has] = code
    n_soma = int((src == 0).sum()); n_tosoma = int((src == 1).sum())
    n_cent = 0
    if CENTROIDS.is_file():
        c = np.load(CENTROIDS, allow_pickle=False)
        assert (c["body_id"] == ids).all(), "centroid file is not in graph order"
        cen = c["centroid_vox"]
        use = (src == 3) & ~np.isnan(cen).any(axis=1)
        xyz[use] = cen[use]
        src[use] = 2
        n_cent = int(use.sum())
    else:
        print(f"WARNING: {CENTROIDS} missing; neurons without a soma get no position", file=sys.stderr)
    return xyz, src, {"soma": n_soma, "tosoma": n_tosoma, "synapse_centroid": n_cent, "none": int((src == 3).sum())}


def activity(g, sensory: np.ndarray) -> tuple[np.ndarray, float]:
    n = len(sensory)
    indptr = g["indptr"].astype(np.int64); indices = g["indices"].astype(np.int32)
    sign = g["edge_sign"].astype(np.float32)
    A = sp.csr_matrix((sign, indices, indptr), shape=(n, n))       # rows pre, cols post, entries = sign
    At = A.T.tocsr()                                                # agg = At @ h
    in_deg = np.diff(At.indptr).astype(np.float32)
    inv = np.where(in_deg > 0, 1.0 / np.maximum(in_deg, 1), 0.0).astype(np.float32)
    rng = np.random.default_rng(SEED)
    drive = np.zeros(n, dtype=np.float32)
    drive[sensory] = rng.random(sensory.sum(), dtype=np.float32)
    h = np.zeros(n, dtype=np.float32)
    frames = np.empty((T, n), dtype=np.float32)
    for t in range(T):
        pre = (At @ h) * inv + drive
        h = 0.5 * h + 0.5 * np.maximum(pre, 0.0)
        frames[t] = h
    act_max = float(frames.max())
    return frames, act_max


def stratified_sample(role: np.ndarray, valid: np.ndarray, k: int, rng) -> np.ndarray:
    """Proportional by role among positioned neurons; a role smaller than its quota is kept whole."""
    idx = np.flatnonzero(valid)
    roles = role[idx]
    out = []
    for r in np.unique(roles):
        members = idx[roles == r]
        quota = int(round(k * len(members) / len(idx)))
        out.append(members if len(members) <= quota else rng.choice(members, quota, replace=False))
    s = np.concatenate(out)
    if len(s) > k:                      # rounding can overshoot by a few; drop at random
        s = rng.choice(s, k, replace=False)
    return np.sort(s.astype(np.uint32))


def main() -> int:
    g = np.load(DATA / "graph.npz", allow_pickle=False)
    meta_in = json.loads((DATA / "graph_meta.json").read_text())
    ids = g["body_id"].astype(np.int64)
    n = len(ids)
    sc = g["superclass"]
    role = np.zeros(n, dtype=np.uint8)
    role[np.isin(sc, list(SENSORY_SC))] = 1
    role[np.isin(sc, list(DESCENDING_SC))] = 2
    role[np.isin(sc, list(MOTOR_SC))] = 3
    nt_class = g["nt_class_neuron"].astype(np.uint8)
    counts = {"sensory": int((role == 1).sum()), "descending": int((role == 2).sum()), "motor": int((role == 3).sum()),
              "other": int((role == 0).sum())}
    assert counts["sensory"] == meta_in["n_sensory"] and counts["descending"] == meta_in["n_descending"] \
        and counts["motor"] == meta_in["n_motor"], "role counts disagree with graph_meta.json"

    xyz_vox, pos_src, pos_counts = positions(ids)
    xyz_um = (xyz_vox * VOXEL_UM).astype(np.float32)
    valid = ~np.isnan(xyz_um).any(axis=1)
    print("positions:", pos_counts, file=sys.stderr)
    print("missing by role:", {k: int(((role == v) & ~valid).sum()) for k, v in
                               (("sensory", 1), ("descending", 2), ("motor", 3), ("other", 0))}, file=sys.stderr)

    frames, act_max = activity(g, role == 1)
    # square-root shade so the many small activities stay visible; byte 0 means exactly "not active" (h == 0)
    frames_u8 = np.clip(np.rint(np.sqrt(frames / act_max) * 255.0), 0, 255).astype(np.uint8)
    frames_u8[(frames > 0) & (frames_u8 == 0)] = 1
    assert ((frames_u8 > 0) == (frames > 0)).all()
    print(f"activity max {act_max:.4f}; active (>0) per step:", [int((f > 0).sum()) for f in frames], file=sys.stderr)

    rng = np.random.default_rng(SEED)
    sample = stratified_sample(role, valid, SAMPLE_N, rng)

    VIZ.mkdir(exist_ok=True)
    # points.bin: xyz float32 (NaN where no position), role, nt_class, pos_source
    xyz_out = xyz_um.copy()
    with (VIZ / "points.bin").open("wb") as f:
        f.write(xyz_out.tobytes(order="C")); f.write(role.tobytes()); f.write(nt_class.tobytes()); f.write(pos_src.tobytes())
    (VIZ / "activity_frames.bin").write_bytes(frames_u8.tobytes(order="C"))
    (VIZ / "sample40k.bin").write_bytes(sample.tobytes())

    ext = xyz_um[valid]
    meta = {
        "n_neurons": n, "n_positioned": int(valid.sum()), "n_unpositioned": int((~valid).sum()),
        "position_sources": pos_counts,
        "unpositioned_by_role": {k: int(((role == v) & ~valid).sum()) for k, v in
                                 (("sensory", 1), ("descending", 2), ("motor", 3), ("other", 0))},
        "role_counts": counts,
        "nt_class_counts": {k: int((nt_class == v).sum()) for k, v in
                            (("excitatory", 0), ("inhibitory", 1), ("modulatory", 2), ("unclear", 3))},
        "pct_edges_excitatory": meta_in["pct_edges_excitatory"], "pct_edges_inhibitory": meta_in["pct_edges_inhibitory"],
        "n_edges_at_threshold": meta_in["n_edges_at_threshold"], "threshold": meta_in["threshold"],
        "units": "micrometres (8 nm voxels x 0.008)",
        "axes": {"x": "lateral (the animal's left at high x)", "y": "dorsal (low) to ventral (high)",
                 "z": "anterior (brain, low) to posterior (ventral nerve cord, high)"},
        "extent_um": {"min": ext.min(axis=0).round(1).tolist(), "max": ext.max(axis=0).round(1).tolist(),
                      "center": ext.mean(axis=0).round(1).tolist()},
        "points_bin": {"xyz_float32_bytes": int(xyz_out.nbytes), "role_offset": int(xyz_out.nbytes),
                       "nt_class_offset": int(xyz_out.nbytes + n), "pos_source_offset": int(xyz_out.nbytes + 2 * n),
                       "total_bytes": int(xyz_out.nbytes + 3 * n)},
        "activity": {"T": T, "seed": SEED, "act_max": act_max, "encoding": "uint8 = round(255 * sqrt(h / act_max)), floored to 1 where h > 0; 0 means not active",
                     "method": "forward pass of the frozen signed graph, unit gains, in-degree normalisation, leak 0.5, "
                               "random uniform(0,1) drive on sensory neurons held constant; placeholder for the trained run",
                     "active_per_step": [int((f > 0).sum()) for f in frames]},
        "sample": {"n": int(len(sample)), "method": "stratified by role among positioned neurons"},
        "sources": {"graph.npz": sha256(DATA / "graph.npz"), ANNOT.name: sha256(ANNOT),
                    "synapse_centroids.npz": sha256(CENTROIDS) if CENTROIDS.is_file() else None},
        "centroid_meta": json.loads(str(np.load(CENTROIDS, allow_pickle=False)["meta"])) if CENTROIDS.is_file() else None,
    }
    (VIZ / "points_meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps({k: meta[k] for k in ("n_positioned", "n_unpositioned", "position_sources", "extent_um")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
