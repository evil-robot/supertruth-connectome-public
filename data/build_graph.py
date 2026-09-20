"""Build a signed sparse adjacency matrix from the MaleCNS v1.0 flat-connectome release.

Inputs (data/malecns/, downloaded from gs://flyem-male-cns/v1.0/connectome-data/flat-connectome/):
    body-annotations-male-cns-v1.0-minconf-0.5.feather   one row per body; neurons = rows with a superclass
    body-neurotransmitters-male-cns-v1.0.feather          per-body consensus_nt
    connectome-weights-male-cns-v1.0-minconf-0.5.feather  body_pre, body_post, weight (synapse count)

Output data/malecns/graph.npz (CSR, rows = presynaptic, cols = postsynaptic) plus graph_meta.json.

Sign convention (Dale's law, one sign per presynaptic neuron, applied to all its outgoing edges):
    acetylcholine                  +1
    gaba, glutamate, histamine     -1   (fly Glu acts mostly through GluCl; His through HisCl)
    dopamine, octopamine, serotonin  modulatory: nt_sign_neuron = 0; edge sign set by --modulatory
    unclear / no NT row              nt_sign_neuron = 0; edge sign set by --unclear
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.feather as feather
import scipy.sparse as sp

HERE = Path(__file__).resolve().parent
DATA = HERE / "malecns"
ANNOT = DATA / "body-annotations-male-cns-v1.0-minconf-0.5.feather"
NT = DATA / "body-neurotransmitters-male-cns-v1.0.feather"
WEIGHTS = DATA / "connectome-weights-male-cns-v1.0-minconf-0.5.feather"

EXCIT = {"acetylcholine"}
INHIB = {"gaba", "glutamate", "histamine"}
MODUL = {"dopamine", "octopamine", "serotonin"}

# nt_class codes stored per neuron
NT_CLASS = {"excitatory": 0, "inhibitory": 1, "modulatory": 2, "unclear": 3}

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


def load_neurons() -> pd.DataFrame:
    ann = feather.read_feather(ANNOT, columns=["bodyId", "superclass", "class", "type", "somaSide"])
    ann = ann[ann["superclass"].notna()].copy()
    nt = feather.read_feather(NT, columns=["body", "consensus_nt", "predicted_nt_confidence"])
    nt = nt.rename(columns={"body": "bodyId"})
    df = ann.merge(nt, on="bodyId", how="left")
    df["consensus_nt"] = df["consensus_nt"].fillna("unclear").astype(str)
    df["predicted_nt_confidence"] = df["predicted_nt_confidence"].astype("float32")
    for c in ("superclass", "class", "type", "somaSide"):
        df[c] = df[c].fillna("").astype(str)
    df["bodyId"] = df["bodyId"].astype(np.int64)
    df = df.sort_values("bodyId").reset_index(drop=True)
    assert df["bodyId"].is_unique, "duplicate bodyId after merge"

    nt_sign = np.zeros(len(df), dtype=np.int8)
    nt_class = np.full(len(df), NT_CLASS["unclear"], dtype=np.int8)
    lab = df["consensus_nt"].to_numpy()
    nt_sign[np.isin(lab, list(EXCIT))] = 1
    nt_sign[np.isin(lab, list(INHIB))] = -1
    nt_class[np.isin(lab, list(EXCIT))] = NT_CLASS["excitatory"]
    nt_class[np.isin(lab, list(INHIB))] = NT_CLASS["inhibitory"]
    nt_class[np.isin(lab, list(MODUL))] = NT_CLASS["modulatory"]
    df["nt_sign"] = nt_sign
    df["nt_class"] = nt_class
    return df


def stream_edges(ids: np.ndarray, threshold: int):
    """Stream the weights table; return (pre_idx, post_idx, weight) for neuron->neuron edges >= threshold,
    plus counts of all neuron->neuron rows (any weight) for the summary."""
    reader = pa.ipc.open_file(WEIGHTS)
    names = reader.schema.names
    for need in ("body_pre", "body_post", "weight"):
        if need not in names:
            sys.exit(f"column {need!r} not in weights table: {names}")
    idset = pa.array(ids)
    pre_parts, post_parts, w_parts = [], [], []
    raw_rows = 0
    nn_rows = 0          # neuron->neuron rows at any weight
    nn_syn = 0           # synapses in those rows
    t0 = time.time()
    nb = reader.num_record_batches
    for i in range(nb):
        b = reader.get_batch(i).select(["body_pre", "body_post", "weight"])
        raw_rows += b.num_rows
        mask = pc.and_(pc.is_in(b.column("body_pre"), value_set=idset),
                       pc.is_in(b.column("body_post"), value_set=idset))
        b = b.filter(mask)
        if b.num_rows == 0:
            continue
        w = b.column("weight").to_numpy()
        nn_rows += b.num_rows
        nn_syn += int(w.sum())
        keep = w >= threshold
        if not keep.any():
            continue
        pre_parts.append(b.column("body_pre").to_numpy()[keep])
        post_parts.append(b.column("body_post").to_numpy()[keep])
        w_parts.append(w[keep])
        if (i + 1) % 50 == 0 or i + 1 == nb:
            print(f"  batch {i + 1}/{nb}  raw rows {raw_rows:,}  kept {sum(len(p) for p in pre_parts):,}  "
                  f"{time.time() - t0:.0f}s", file=sys.stderr)
    pre_b = np.concatenate(pre_parts)
    post_b = np.concatenate(post_parts)
    w = np.concatenate(w_parts).astype(np.int64)
    pre = np.searchsorted(ids, pre_b)
    post = np.searchsorted(ids, post_b)
    assert (ids[pre] == pre_b).all() and (ids[post] == post_b).all()
    return pre.astype(np.int32), post.astype(np.int32), w, dict(raw_rows=raw_rows, nn_rows=nn_rows, nn_syn=nn_syn)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--threshold", type=int, default=5, help="keep edges with >= this many synapses (default 5)")
    ap.add_argument("--modulatory", choices=["plus", "minus", "zero"], default="plus",
                    help="edge sign for dopamine/octopamine/serotonin presynaptic neurons (default plus)")
    ap.add_argument("--unclear", choices=["plus", "minus", "zero"], default="plus",
                    help="edge sign for presynaptic neurons with unclear/no NT prediction (default plus)")
    ap.add_argument("--out", type=Path, default=DATA / "graph.npz")
    args = ap.parse_args()
    for p in (ANNOT, NT, WEIGHTS):
        if not p.is_file():
            sys.exit(f"missing {p}")

    policy = {"plus": 1, "minus": -1, "zero": 0}
    neurons = load_neurons()
    ids = neurons["bodyId"].to_numpy()
    N = len(ids)
    print(f"neurons (superclass non-null): {N:,}", file=sys.stderr)

    pre, post, w, counts = stream_edges(ids, args.threshold)
    # Collapse any duplicate (pre, post) rows by summing (the release should have none).
    A = sp.coo_matrix((w, (pre, post)), shape=(N, N)).tocsr()
    A.sum_duplicates()
    A.sort_indices()
    dup = len(w) - A.nnz

    # Edge sign from the presynaptic neuron, aligned with CSR data.
    row_of = np.repeat(np.arange(N, dtype=np.int32), np.diff(A.indptr))
    nt_sign = neurons["nt_sign"].to_numpy()
    nt_class = neurons["nt_class"].to_numpy()
    edge_sign = nt_sign[row_of].astype(np.int8)
    mod_e = nt_class[row_of] == NT_CLASS["modulatory"]
    unc_e = nt_class[row_of] == NT_CLASS["unclear"]
    edge_sign[mod_e] = policy[args.modulatory]
    edge_sign[unc_e] = policy[args.unclear]

    src_hashes = {p.name: {"sha256": sha256(p), "bytes": p.stat().st_size} for p in (ANNOT, NT, WEIGHTS)}

    np.savez_compressed(
        args.out,
        body_id=ids,
        superclass=neurons["superclass"].to_numpy().astype(str),
        cell_class=neurons["class"].to_numpy().astype(str),
        cell_type=neurons["type"].to_numpy().astype(str),
        soma_side=neurons["somaSide"].to_numpy().astype(str),
        nt_label=neurons["consensus_nt"].to_numpy().astype(str),
        nt_confidence=neurons["predicted_nt_confidence"].to_numpy(),
        nt_sign_neuron=nt_sign,          # +1 / -1 / 0 (0 = modulatory or unclear)
        nt_class_neuron=nt_class,        # 0 excit, 1 inhib, 2 modulatory, 3 unclear
        indptr=A.indptr.astype(np.int64),
        indices=A.indices.astype(np.int32),   # postsynaptic index
        syn_count=A.data.astype(np.int32),
        edge_sign=edge_sign,             # +1 / -1 (or 0 if a policy was 'zero')
        threshold=np.int32(args.threshold),
        modulatory_policy=np.array(args.modulatory),
        unclear_policy=np.array(args.unclear),
    )

    # ---------------- summary (every number computed above) ----------------
    E = A.nnz
    syn_total = int(A.data.sum())
    outdeg = np.diff(A.indptr)
    indeg = np.bincount(A.indices, minlength=N)
    q = [0, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1.0]
    sc = neurons["superclass"]
    n_sensory = int(sc.isin(SENSORY_SC).sum())
    n_desc = int(sc.isin(DESCENDING_SC).sum())
    n_motor = int(sc.isin(MOTOR_SC).sum())
    nt_counts = neurons["consensus_nt"].value_counts()
    exc_e = edge_sign > 0
    inh_e = edge_sign < 0
    known_e = ~(mod_e | unc_e)

    summary = {
        "source_files": src_hashes,
        "threshold": args.threshold,
        "modulatory_policy": args.modulatory,
        "unclear_policy": args.unclear,
        "n_neurons": N,
        "n_bodies_in_annotation_table": int(pa.ipc.open_file(ANNOT).read_all().num_rows),
        "weights_table_rows_all_bodies": counts["raw_rows"],
        "neuron_to_neuron_rows_any_weight": counts["nn_rows"],
        "neuron_to_neuron_synapses_any_weight": counts["nn_syn"],
        "duplicate_pairs_collapsed": int(dup),
        "n_edges_at_threshold": int(E),
        "synapses_at_threshold": syn_total,
        "pct_edges_excitatory": round(100 * exc_e.mean(), 2),
        "pct_edges_inhibitory": round(100 * inh_e.mean(), 2),
        "pct_synapses_excitatory": round(100 * A.data[exc_e].sum() / syn_total, 2),
        "pct_edges_from_known_ach_gaba_glu_his": round(100 * known_e.mean(), 2),
        "pct_edges_from_modulatory": round(100 * mod_e.mean(), 2),
        "pct_edges_from_unclear": round(100 * unc_e.mean(), 2),
        "neurons_with_zero_edges_at_threshold": int(((outdeg == 0) & (indeg == 0)).sum()),
        "out_degree_quantiles": dict(zip([str(x) for x in q], np.quantile(outdeg, q).astype(int).tolist())),
        "in_degree_quantiles": dict(zip([str(x) for x in q], np.quantile(indeg, q).astype(int).tolist())),
        "nt_label_counts": {k: int(v) for k, v in nt_counts.items()},
        "superclass_counts": {k: int(v) for k, v in sc.value_counts().items()},
        "n_sensory": n_sensory,
        "n_descending": n_desc,
        "n_motor": n_motor,
        "n_cell_types": int((neurons["type"] != "").sum() and neurons.loc[neurons["type"] != "", "type"].nunique()),
        "output": str(args.out),
        "output_bytes": args.out.stat().st_size,
    }
    (args.out.with_name("graph_meta.json")).write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
