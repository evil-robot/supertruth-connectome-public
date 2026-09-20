"""One run = (task, arm, seed) -> runs/{task}/{arm}/seed{S}/ with run.json, best.safetensors, standardization.json,
metrics.json (TEST, read once), and a line in runs/eval_ledger.jsonl.

  .venv/bin/python scripts/run_arm.py --task dti --arm connectome --seed 1 [--batch 64] [--epochs 20]
      [--patience 3] [--lr 1e-3] [--T 8] [--device mps] [--reason "..."]

Settings identical for every gradient arm (pilot brief): AdamW lr 1e-3 with cosine decay over max epochs,
weight decay 0.01, grad clip 1.0, early stopping patience 3 on VAL loss, max 20 epochs, T = 8, batch from
runs/batch_choice.json (measured once by scripts/measure_batch.py). Shuffle control: degree-preserving double-edge
swaps with swaps_per_edge = 10 (fully mixed null). Ridge: closed form; lambda from {0.01, 0.1, 1, 10, 100} by VAL
loss. Features are standardized with TRAIN statistics only (flytrust.data_adapters.Standardizer).

TEST is read once per (task, arm, seed); a second evaluation needs --reason (DECISION_RULES rule 9).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from safetensors.torch import load_file

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flytrust.controls import build_arm, RidgeReadout, ARMS                                   # noqa: E402
from flytrust.data_adapters import (load_teacher, load_split_json, Standardizer, TEACHER_FILE,  # noqa: E402
                                    MANIFEST_SHA256, DTI_DIMS, DTI_WEIGHTS, SPEC_BY_NAME)
from flytrust.graph import load_graph, ROOT, sha256_file                                       # noqa: E402
from flytrust.metrics import loss_terms, mae_per_dim, accuracy, macro_f1, macro_f1_supported, calibration  # noqa: E402
from flytrust.model import describe                                                            # noqa: E402
from flytrust.train import TrainConfig, Trainer, seed_all, peak_rss_bytes                     # noqa: E402

SWAPS_PER_EDGE = 10.0
RIDGE_GRID = (0.01, 0.1, 1.0, 10.0, 100.0)
LEDGER = None   # set from --out-root in main()


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def js_round(x: float) -> int:
    return int(np.floor(x + 0.5))


def recompute_composite(dims_0_100: np.ndarray) -> np.ndarray:
    """pipeline.ts computeDTIResult: naive left-to-right weighted sum, Math.round (half up)."""
    out = np.empty(len(dims_0_100), dtype=np.int64)
    for r, row in enumerate(dims_0_100):
        acc = 0.0
        for w, d in zip(DTI_WEIGHTS, row):
            acc += w * float(d)
        out[r] = js_round(acc / 100.0)
    return out


@torch.no_grad()
def predict(model, X: torch.Tensor, idx: np.ndarray, device, batch: int) -> dict:
    model.eval()
    idx_t = torch.as_tensor(idx, dtype=torch.long)
    outs = None
    for s in range(0, len(idx_t), batch):
        out = model(X[idx_t[s:s + batch]].to(device))
        if outs is None:
            outs = {k: [] for k in out}
        for k, v in out.items():
            outs[k].append(v.float().cpu())
    return {k: torch.cat(v) for k, v in outs.items()}


def test_metrics(task: str, spec, out: dict, Y: dict, idx: np.ndarray) -> dict:
    y = {k: v[torch.as_tensor(idx, dtype=torch.long)] for k, v in Y.items()}
    m = {"n_test": int(len(idx))}
    loss = loss_terms(spec, out, y)
    m["test_loss"] = float(sum(v.item() for v in loss.values()))
    m["test_loss_terms"] = {k: v.item() for k, v in loss.items()}
    if task == "dti":
        per = mae_per_dim(out["dims"], y["dims"])
        m["dims_mae"] = dict(zip(DTI_DIMS, per))
        m["dims_mae_mean"] = float(np.mean(per))
        m["composite_mae_direct"] = mae_per_dim(out["composite"], y["composite"])[0]
        dims_hat = np.clip(out["dims"].numpy() * 100.0, 0, 100)
        comp_re = recompute_composite(dims_hat)
        comp_true = np.rint(y["composite"].numpy().ravel() * 100.0)
        m["composite_mae_recomputed_from_dims"] = float(np.abs(comp_re - comp_true).mean())
        cls, logits, ytrue, n_cls = "tier", out["tier"], y["tier"], 5
    else:
        m["bii_mae"] = float((out["bii"] - y["bii"]).abs().mean().item())
        m["bii_mae_x100"] = m["bii_mae"] * 100.0
        cls, logits, ytrue, n_cls = "gate", out["gate"], y["gate"], 4
    m[f"{cls}_acc"] = accuracy(logits, ytrue)
    m[f"{cls}_macro_f1_all_classes"] = macro_f1(logits, ytrue, n_cls)
    sup = macro_f1_supported(logits, ytrue, n_cls, min_support=30)
    m[f"{cls}_macro_f1"] = sup["macro_f1"]
    m[f"{cls}_macro_f1_classes_used"] = [spec.classes[cls][c] for c in sup["classes_used"]]
    m[f"{cls}_support"] = {spec.classes[cls][c]: int((ytrue == c).sum()) for c in range(n_cls)}
    m["calibration"] = calibration(logits, ytrue, n_cls, n_bins=10)
    return m


def ledger_check(task: str, arm: str, seed: int, reason: str | None):
    if LEDGER is None or not LEDGER.exists():
        return
    for line in LEDGER.read_text().splitlines():
        e = json.loads(line)
        if (e["task"], e["arm"], e["seed"]) == (task, arm, seed) and not reason:
            raise SystemExit(f"TEST already read for {task}/{arm}/seed{seed} at {e['utc']}; pass --reason to read again")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", choices=("dti", "bii"), required=True)
    ap.add_argument("--arm", choices=ARMS, required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--batch", type=int, default=0, help="0 = read runs/batch_choice.json")
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--patience", type=int, default=3)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--T", type=int, default=8)
    ap.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    ap.add_argument("--reason", default=None, help="required to read TEST a second time for this (task, arm, seed)")
    ap.add_argument("--out-root", type=Path, default=ROOT / "runs")
    a = ap.parse_args(argv)

    global LEDGER
    LEDGER = a.out_root / "eval_ledger.jsonl"
    t_start = time.perf_counter()
    started = utc()
    ledger_check(a.task, a.arm, a.seed, a.reason)
    out = a.out_root / a.task / a.arm / f"seed{a.seed}"
    out.mkdir(parents=True, exist_ok=True)
    log_path = out / "log.txt"

    def log(*parts):
        line = " ".join(str(p) for p in parts)
        print(line, flush=True)
        with open(log_path, "a") as f:
            f.write(line + "\n")

    # data + provenance
    teacher_path = ROOT / TEACHER_FILE[a.task]
    teacher_sha = sha256_file(teacher_path)
    if teacher_sha != MANIFEST_SHA256[a.task]:
        raise SystemExit(f"{teacher_path} sha256 {teacher_sha} != MANIFEST {MANIFEST_SHA256[a.task]}")
    spec = SPEC_BY_NAME[a.task]
    ids, X, Y, _labels = load_teacher(a.task, ROOT)
    split_path = ROOT / "splits" / f"{a.task}_seed{a.seed}.json"
    split = load_split_json(split_path, ids)
    tr, va, te = split["train"], split["val"], split["test"]
    scaler = Standardizer.fit(X, tr, partition="train")
    scaler.save(out / "standardization.json")
    Xs = scaler.transform(X)
    if a.batch == 0:
        choice = json.loads((ROOT / "runs" / "batch_choice.json").read_text())
        a.batch = int(choice["choice"])
    log(f"[{started}] {a.task}/{a.arm}/seed{a.seed}: X {tuple(Xs.shape)} train {len(tr)} val {len(va)} test {len(te)} batch {a.batch}")

    cfg = TrainConfig(epochs=a.epochs, batch_size=a.batch, lr=a.lr, weight_decay=0.01, grad_clip=1.0, warmup_steps=0,
                      patience=a.patience, seed=a.seed, device=a.device, T=a.T, arm=a.arm, spec=a.task,
                      graph_k=0, norm="total_gain", ridge_lambda=1.0, determinism_check=True,
                      extra={"swaps_per_edge": SWAPS_PER_EDGE if a.arm == "shuffle" else None,
                             "lr_schedule": "cosine over max epochs, no warmup", "ridge_grid": list(RIDGE_GRID) if a.arm == "ridge" else None})

    graph = load_graph()
    seed_all(a.seed)
    device = torch.device(a.device)
    t_build = time.perf_counter()
    if a.arm == "ridge":
        best_lam, best_loss = None, float("inf")
        xtr = Xs[torch.as_tensor(tr)].to(device); ytr = {k: v[torch.as_tensor(tr)].to(device) for k, v in Y.items()}
        xva = Xs[torch.as_tensor(va)].to(device); yva = {k: v[torch.as_tensor(va)].to(device) for k, v in Y.items()}
        grid_losses = {}
        for lam in RIDGE_GRID:
            m = RidgeReadout(Xs.shape[1], spec, lam=lam).to(device).fit(xtr, ytr)
            with torch.no_grad():
                l = float(sum(v.item() for v in loss_terms(spec, m(xva), yva).values()))
            grid_losses[str(lam)] = l
            if l < best_loss:
                best_lam, best_loss = lam, l
        cfg.ridge_lambda = best_lam
        cfg.extra["ridge_grid_val_loss"] = grid_losses
        log(f"ridge lambda by VAL loss: {grid_losses} -> {best_lam}")
        model, meta = build_arm("ridge", graph, Xs.shape[1], spec, T=a.T, device=a.device, seed=a.seed, lam=best_lam)
    elif a.arm == "shuffle":
        model, meta = build_arm("shuffle", graph, Xs.shape[1], spec, T=a.T, device=a.device, seed=a.seed,
                                norm=cfg.norm, swaps_per_edge=SWAPS_PER_EDGE)
    elif a.arm in ("connectome", "er"):
        model, meta = build_arm(a.arm, graph, Xs.shape[1], spec, T=a.T, device=a.device, seed=a.seed, norm=cfg.norm)
    else:
        model, meta = build_arm(a.arm, graph, Xs.shape[1], spec, T=a.T, device=a.device, seed=a.seed)
    build_seconds = time.perf_counter() - t_build
    log(describe(model))
    if a.arm in ("shuffle", "er"):
        g0, g1 = graph.summary(), meta["graph"]
        assert (g1["n"], g1["e"]) == (g0["n"], g0["e"]), "null graph must match N and E"
    meta.update({
        "task": a.task, "seed": a.seed, "started_utc": started, "build_seconds": build_seconds,
        "teacher_file": TEACHER_FILE[a.task], "teacher_sha256": teacher_sha, "teacher_sha256_manifest": MANIFEST_SHA256[a.task],
        "split_file": str(split_path.relative_to(ROOT)), "split_sha256": sha256_file(split_path),
        "split_meta": {k: v for k, v in split["meta"].items() if k != "counts"}, "split_counts": split["meta"]["counts"],
        "standardization": {"file": "standardization.json", **scaler.to_dict()},
        "batch_choice": json.loads((ROOT / "runs" / "batch_choice.json").read_text()) if (ROOT / "runs" / "batch_choice.json").exists() else None,
        "hyperparameters": {**asdict(cfg), "swaps_per_edge": SWAPS_PER_EDGE if a.arm == "shuffle" else None},
        "real_graph": graph.summary(), "graph_meta": {k: graph.meta.get(k) for k in ("threshold", "modulatory_policy", "unclear_policy", "n_neurons", "n_edges_at_threshold")},
    })

    trainer = Trainer(model, spec, Xs, Y, tr, va, cfg, out, run_meta=meta, log=log)
    t_fit = time.perf_counter()
    res = trainer.fit_closed_form() if isinstance(model, RidgeReadout) else trainer.fit()
    fit_seconds = time.perf_counter() - t_fit

    # TEST, once, from the best checkpoint
    sd = load_file(str(out / "best.safetensors"))
    model.load_state_dict({k: v.to(device) for k, v in sd.items()})
    t_eval = time.perf_counter()
    out_te = predict(model, Xs, te, device, a.batch)
    eval_seconds = time.perf_counter() - t_eval
    m = test_metrics(a.task, spec, out_te, Y, te)
    with torch.no_grad():
        model.eval()
        xb = Xs[torch.as_tensor(te[: a.batch])].to(device)
        p1, p2 = model(xb), model(xb)
        det = all(torch.equal(p1[k], p2[k]) for k in p1)
    hist = res["history"]
    total_seconds = time.perf_counter() - t_start
    m.update({
        "task": a.task, "arm": a.arm, "seed": a.seed, "split": "test", "split_sha256": meta["split_sha256"],
        "teacher_sha256": teacher_sha, "graph": meta["graph"], "trainable_params": meta["trainable_params"],
        "fitted_params": int(model.W.numel()) if isinstance(model, RidgeReadout) else meta["trainable_params"],
        "deterministic_test_forward": bool(det), "deterministic_val_per_epoch": [h.get("deterministic") for h in hist],
        "epochs_run": len(hist), "best_epoch": res["best_epoch"], "best_val_loss": res["best_val_loss"],
        "early_stopped": len(hist) < a.epochs and not isinstance(model, RidgeReadout),
        "wall_seconds": {"total": total_seconds, "build": build_seconds, "fit": fit_seconds, "test_eval": eval_seconds,
                         "per_epoch_train": [h.get("epoch_train_seconds") for h in hist]},
        "peak_rss_bytes": peak_rss_bytes(), "peak_device_bytes_sampled": trainer.peak_dev,
        "batch": a.batch, "device": a.device, "evaluated_utc": utc(),
    })
    (out / "metrics.json").write_text(json.dumps(m, indent=2, default=str) + "\n")
    msha = hashlib.sha256((out / "metrics.json").read_bytes()).hexdigest()
    LEDGER.parent.mkdir(exist_ok=True)
    with open(LEDGER, "a") as f:
        f.write(json.dumps({"task": a.task, "arm": a.arm, "seed": a.seed, "utc": m["evaluated_utc"],
                            "reason": a.reason, "metrics_sha256": msha}) + "\n")
    headline = (f"composite MAE {m['composite_mae_direct']:.2f} tier acc {m['tier_acc']:.3f}" if a.task == "dti"
                else f"BII MAE {m['bii_mae']:.4f} gate acc {m['gate_acc']:.3f}")
    log(f"TEST {a.task}/{a.arm}/seed{a.seed}: {headline}  epochs {len(hist)}  det {det}  {total_seconds / 60:.1f} min")


if __name__ == "__main__":
    main()
