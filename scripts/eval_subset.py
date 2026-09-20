"""Sidecar TEST re-read for finished runs: per-record errors + metrics on the language-model arm's exact record ids.

  .venv/bin/python scripts/eval_subset.py --reason "..." [--ids-from llm_arm/llm_runs/20260920T154525Z]
                                          [--task dti --arm connectome --seed 1] [--force]

For every runs/<task>/<arm>/seed<S>/ that has metrics.json and best.safetensors (all of them by default; later seeds are
picked up automatically), rebuild the model from run.json, load the checkpoint and the run's TRAIN-fit standardizer,
run ONE forward pass over the full TEST split, and write:
  per_record.parquet        one row per TEST record: id, truth, prediction, absolute error per head (feeds the
                            protocol 8.2 hierarchical bootstrap in scripts/collect_results.py)
  metrics_subset300.json    the run_arm.test_metrics block restricted to the ids the language-model arm scored
                            (from <ids-from>/calls.jsonl), so arms are compared on identical records
Rule 9: this is a second read of TEST, so --reason is required and one line per (task, arm, seed) is appended to
runs/eval_ledger.jsonl with that reason. Verifier: the full-TEST metrics recomputed here must equal metrics.json
(composite direct and recomputed, tier or gate accuracy, every dimension) to 1e-5, or the model was rebuilt wrong
(e.g. a different shuffle) and the run aborts before writing anything.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import torch
from safetensors.torch import load_file

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flytrust.controls import build_arm                                                     # noqa: E402
from flytrust.data_adapters import load_teacher, load_split_json, Standardizer, TEACHER_FILE, MANIFEST_SHA256, DTI_DIMS, SPEC_BY_NAME  # noqa: E402
from flytrust.graph import load_graph, ROOT, sha256_file                                     # noqa: E402
from scripts.run_arm import predict, test_metrics, recompute_composite                       # noqa: E402

DEFAULT_IDS = ROOT / "llm_arm" / "llm_runs" / "20260920T154525Z"
TOL = 1e-5


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def llm_ids(run_dir: Path) -> tuple[list[str], dict]:
    ids = []
    for line in (run_dir / "calls.jsonl").read_text().splitlines():
        rid = json.loads(line)["record_id"]
        if rid not in ids:
            ids.append(rid)
    return ids, {"run": run_dir.name, "calls_file_sha256": sha256_file(run_dir / "calls.jsonl"), "n_ids": len(ids)}


def finished_runs(task: str | None, arm: str | None, seed: int | None):
    for p in sorted((ROOT / "runs").glob("*/*/seed*/metrics.json")):
        t, a, s = p.parts[-4], p.parts[-3], int(p.parts[-2][4:])
        if t not in ("dti", "bii") or (task and t != task) or (arm and a != arm) or (seed and s != seed):
            continue
        if (p.parent / "best.safetensors").exists() and (p.parent / "run.json").exists():
            yield t, a, s, p.parent


def rebuild(task: str, arm: str, seed: int, out: Path, graph, in_dim: int, device: str):
    run = json.loads((out / "run.json").read_text())
    cfg = run["config"]; spec = SPEC_BY_NAME[task]
    kw = {}
    if arm == "ridge":
        kw["lam"] = cfg["ridge_lambda"]
    elif arm == "shuffle":
        kw.update(norm=cfg["norm"], swaps_per_edge=run["run_meta"]["hyperparameters"]["swaps_per_edge"])
    elif arm in ("connectome", "er"):
        kw["norm"] = cfg["norm"]
    torch.manual_seed(seed); np.random.seed(seed)
    model, meta = build_arm(arm, graph, in_dim, spec, T=cfg["T"], device=device, seed=seed, **kw)
    sd = load_file(str(out / "best.safetensors"))
    model.load_state_dict({k: v.to(device) for k, v in sd.items()})
    model.eval()
    return model, spec, run


def check_reproduces(task: str, m_full: dict, m_ref: dict):
    if task == "dti":
        keys = ["composite_mae_direct", "composite_mae_recomputed_from_dims", "tier_acc"] + [("dims_mae", d) for d in DTI_DIMS]
    else:
        keys = ["bii_mae", "gate_acc"]
    bad = []
    for k in keys:
        a = m_full[k[0]][k[1]] if isinstance(k, tuple) else m_full[k]
        b = m_ref[k[0]][k[1]] if isinstance(k, tuple) else m_ref[k]
        if abs(a - b) > TOL:
            bad.append((k, a, b))
    if bad:
        raise SystemExit(f"REBUILD MISMATCH vs metrics.json (model or standardizer differs): {bad}")


def per_record_table(task: str, spec, out_te: dict, Y: dict, te: np.ndarray, ids: list[str], meta: dict) -> pa.Table:
    y = {k: v[torch.as_tensor(te, dtype=torch.long)] for k, v in Y.items()}
    cols = {"record_id": [ids[i] for i in te], "row_index": te.astype(np.int64)}
    if task == "dti":
        dims_hat = np.clip(out_te["dims"].numpy() * 100.0, 0, 100); dims_true = y["dims"].numpy() * 100.0
        for j, d in enumerate(DTI_DIMS):
            cols[f"{d}_true"] = dims_true[:, j]; cols[f"{d}_pred"] = dims_hat[:, j]; cols[f"abs_err_{d}"] = np.abs(dims_hat[:, j] - dims_true[:, j])
        comp_true = np.rint(y["composite"].numpy().ravel() * 100.0)
        comp_direct = out_te["composite"].numpy().ravel() * 100.0
        comp_re = recompute_composite(dims_hat).astype(np.float64)
        cols.update({"composite_true": comp_true, "composite_pred_direct": comp_direct, "composite_pred_recomputed": comp_re,
                     "abs_err_composite_direct": np.abs(comp_direct - y["composite"].numpy().ravel() * 100.0),
                     "abs_err_composite_recomputed": np.abs(comp_re - comp_true)})
        tt = y["tier"].numpy(); tp = out_te["tier"].argmax(1).numpy()
        cols.update({"tier_true": [spec.classes["tier"][c] for c in tt], "tier_pred": [spec.classes["tier"][c] for c in tp], "tier_correct": tt == tp})
    else:
        bt = y["bii"].numpy().ravel(); bp = out_te["bii"].numpy().ravel()
        cols.update({"bii_true": bt, "bii_pred": bp, "abs_err_bii": np.abs(bp - bt)})
        gt = y["gate"].numpy(); gp = out_te["gate"].argmax(1).numpy()
        cols.update({"gate_true": [spec.classes["gate"][c] for c in gt], "gate_pred": [spec.classes["gate"][c] for c in gp], "gate_correct": gt == gp})
    table = pa.table(cols)
    return table.replace_schema_metadata({k: json.dumps(v) for k, v in meta.items()})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reason", required=True, help="rule 9: why TEST is being read again")
    ap.add_argument("--ids-from", type=Path, default=DEFAULT_IDS, help="language-model run dir whose calls.jsonl fixes the record ids (DTI)")
    ap.add_argument("--task", choices=("dti", "bii")); ap.add_argument("--arm"); ap.add_argument("--seed", type=int)
    ap.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    ap.add_argument("--force", action="store_true", help="re-read even when per_record.parquet already exists")
    a = ap.parse_args(argv)
    ledger = ROOT / "runs" / "eval_ledger.jsonl"
    ids300, ids_meta = llm_ids(a.ids_from)
    cache = {}
    graph = None
    done = []
    for task, arm, seed, out in finished_runs(a.task, a.arm, a.seed):
        if (out / "per_record.parquet").exists() and not a.force:
            print(f"skip {task}/{arm}/seed{seed} (per_record.parquet exists; --force to redo)"); continue
        if task not in cache:
            teacher_path = ROOT / TEACHER_FILE[task]
            if sha256_file(teacher_path) != MANIFEST_SHA256[task]:
                raise SystemExit(f"{teacher_path} sha256 differs from MANIFEST")
            cache[task] = load_teacher(task, ROOT)
        ids, X, Y, _ = cache[task]
        split_path = ROOT / "splits" / f"{task}_seed{seed}.json"
        te = load_split_json(split_path, ids)["test"]
        scaler = Standardizer.load(out / "standardization.json")
        Xs = scaler.transform(X)
        if graph is None:
            graph = load_graph()
        batch = json.loads((out / "metrics.json").read_text())["batch"]
        model, spec, run = rebuild(task, arm, seed, out, graph, Xs.shape[1], a.device)
        out_te = predict(model, Xs, te, a.device, batch)                       # the one re-read
        m_full = test_metrics(task, spec, out_te, Y, te)
        check_reproduces(task, m_full, json.loads((out / "metrics.json").read_text()))
        stamp = {"task": task, "arm": arm, "seed": seed, "split": "test", "split_sha256": sha256_file(split_path),
                 "teacher_sha256": MANIFEST_SHA256[task], "checkpoint_sha256": sha256_file(out / "best.safetensors"),
                 "evaluated_utc": utc(), "reason": a.reason, "reproduces_metrics_json_to": TOL}
        pq.write_table(per_record_table(task, spec, out_te, Y, te, ids, stamp), out / "per_record.parquet")
        # subset on the language-model arm's exact ids (DTI ids only; a BII model-arm run would supply its own)
        pos = {ids[i]: k for k, i in enumerate(te)}
        sub_keys = [k for k in (pos.get(r) for r in ids300) if k is not None]
        subset = {"ids_source": ids_meta, "n_ids_in_test": len(sub_keys), **stamp}
        if len(sub_keys) == len(ids300) and len(sub_keys) > 0:
            sel = torch.as_tensor(sub_keys, dtype=torch.long)
            out_sub = {k: v[sel] for k, v in out_te.items()}
            subset.update(test_metrics(task, spec, out_sub, Y, te[sub_keys]))
            subset["record_ids_sha256"] = hashlib.sha256("\n".join(ids300).encode()).hexdigest()
        else:
            subset["note"] = f"{len(sub_keys)} of {len(ids300)} language-model ids fall in this task's TEST split; no subset metrics"
        (out / "metrics_subset300.json").write_text(json.dumps(subset, indent=2, default=str) + "\n")
        msha = hashlib.sha256((out / "metrics_subset300.json").read_bytes()).hexdigest()
        with open(ledger, "a") as f:
            f.write(json.dumps({"task": task, "arm": arm, "seed": seed, "utc": stamp["evaluated_utc"], "reason": a.reason,
                                "metrics_sha256": msha, "kind": "eval_subset: per_record.parquet + metrics_subset300.json"}) + "\n")
        head = (f"subset300 composite recomputed {subset.get('composite_mae_recomputed_from_dims', float('nan')):.2f} direct "
                f"{subset.get('composite_mae_direct', float('nan')):.2f} tier acc {subset.get('tier_acc', float('nan')):.3f}" if task == "dti" and "tier_acc" in subset
                else subset.get("note", ""))
        print(f"{task}/{arm}/seed{seed}: full TEST reproduced to {TOL}; {head}")
        done.append((task, arm, seed))
    print(f"done: {len(done)} run(s)")


if __name__ == "__main__":
    main()
