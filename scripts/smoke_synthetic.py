"""Smoke run on synthetic targets, FULL graph.

1. X random [4096, 64]; Y = a fixed random linear + nonlinear function of X (DTI spec: 8 dims, composite, tier).
2. Full-graph ConnectomeNet, 2 epochs at B=64 on MPS: loss must fall; real epoch time and memory.
3. Shuffled and ER controls: build on the full graph and take one training step.
4. MatchedMLP at the full-graph parameter count; RidgeReadout closed form.
5. Extrapolate epoch time to 20,000 records at B=64 from the measured per-step time and flag if > 10 min.

  .venv/bin/python scripts/smoke_synthetic.py [--device mps] [--epochs 2] [--batch 64] [--T 8]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flytrust.controls import build_arm                                    # noqa: E402
from flytrust.data_adapters import synthetic_dataset, save_npz_dataset, make_splits, load_splits   # noqa: E402
from flytrust.graph import load_graph, ROOT                                # noqa: E402
from flytrust.metrics import loss_terms                                   # noqa: E402
from flytrust.model import DTI_SPEC, count_parameters                     # noqa: E402
from flytrust.train import TrainConfig, run, peak_rss_bytes, device_mem_bytes   # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--T", type=int, default=8)
    ap.add_argument("--n", type=int, default=4096)
    ap.add_argument("--in-dim", type=int, default=64)
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "smoke")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    report = {"args": vars(a) | {"out": str(a.out)}}

    X, Y = synthetic_dataset(a.n, a.in_dim, DTI_SPEC, seed=0)
    data, splits = a.out / "dti_synthetic.npz", a.out / "splits.npz"
    save_npz_dataset(data, X, Y)
    make_splits(splits, a.n, 0.2, seed=0)
    tr, va = load_splits(splits)
    print(f"synthetic DTI set: X {tuple(X.shape)}  train {len(tr)}  val {len(va)}")

    graph = load_graph()
    print("graph:", graph.summary())

    # 2. full-graph connectome, 2 epochs
    cfg = TrainConfig(epochs=a.epochs, batch_size=a.batch, lr=1e-3, device=a.device, T=a.T, arm="connectome",
                      spec="dti", patience=10, seed=0)
    res, trainer = run(cfg, data, splits, a.out / "connectome_full", graph=graph)
    h = res["history"]
    steps_per_epoch = -(-len(tr) // a.batch)
    sec_per_step = h[-1]["epoch_train_seconds"] / steps_per_epoch
    est_20k = sec_per_step * (-(-20000 // a.batch))
    report["connectome_full"] = {
        "trainable_params": count_parameters(trainer.model), "param_breakdown": trainer.model.parameter_breakdown(),
        "first_batch_loss": h[0]["train_first_batch_loss"], "epoch_train_losses": [r["train_loss"] for r in h],
        "epoch_val_losses": [r["val"]["loss"] for r in h], "last_val": h[-1]["val"],
        "epoch_train_seconds": [r["epoch_train_seconds"] for r in h], "steps_per_epoch": steps_per_epoch,
        "seconds_per_step": sec_per_step, "estimated_epoch_seconds_at_20k_records": est_20k,
        "over_10_min_at_20k": est_20k > 600, "peak_device_bytes_sampled": h[-1]["peak_device_bytes_sampled"],
        "peak_rss_bytes": h[-1]["peak_rss_bytes"], "deterministic": [r["deterministic"] for r in h]}
    print(json.dumps(report["connectome_full"], indent=1, default=str))
    del trainer
    if a.device == "mps":
        torch.mps.empty_cache()

    # 4. MatchedMLP through the same trainer for the same epochs (cheap), for a like-for-like curve
    cfg_mlp = TrainConfig(epochs=a.epochs, batch_size=a.batch, lr=1e-3, device=a.device, T=a.T, arm="mlp",
                          spec="dti", patience=10, seed=0)
    res_m, tr_m = run(cfg_mlp, data, splits, a.out / "mlp_full_params", graph=graph)
    hm = res_m["history"]
    report["mlp_trained"] = {"trainable_params": count_parameters(tr_m.model), "target_params": tr_m.run_meta["target_params"],
                             "hidden_width": tr_m.run_meta["hidden_width"],
                             "first_batch_loss": hm[0]["train_first_batch_loss"],
                             "epoch_train_losses": [r["train_loss"] for r in hm],
                             "epoch_val_losses": [r["val"]["loss"] for r in hm], "last_val": hm[-1]["val"],
                             "epoch_train_seconds": [r["epoch_train_seconds"] for r in hm]}
    del tr_m

    # 3. graph controls: three clipped training steps each on the full graph; ridge closed form
    for arm in ("shuffle", "er", "ridge"):
        t0 = time.perf_counter()
        model, meta = build_arm(arm, graph, a.in_dim, DTI_SPEC, T=a.T, device=a.device, seed=0)
        build_s = time.perf_counter() - t0
        entry = {"build_seconds": build_s, "trainable_params": meta["trainable_params"], "graph": meta.get("graph")}
        x = X[tr[: a.batch]].to(a.device); y = {k: v[tr[: a.batch]].to(a.device) for k, v in Y.items()}
        if arm == "ridge":
            model.fit(X[tr].to(a.device), {k: v[tr].to(a.device) for k, v in Y.items()})
            with torch.no_grad():
                entry["val_loss"] = sum(v.item() for v in loss_terms(DTI_SPEC, model(X[va].to(a.device)),
                                                                     {k: v[va].to(a.device) for k, v in Y.items()}).values())
        else:
            opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
            losses = []
            for _ in range(3):
                out = model(x); loss = sum(loss_terms(DTI_SPEC, out, y).values())
                opt.zero_grad(); loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)      # same clip as the trainer
                opt.step(); losses.append(loss.item())
            entry["three_step_losses"] = losses
        entry["peak_rss_bytes"] = peak_rss_bytes(); entry["device_bytes"] = device_mem_bytes(torch.device(a.device))
        report[arm] = entry
        print(arm, json.dumps(entry, default=str))
        del model
        if a.device == "mps":
            torch.mps.empty_cache()

    (a.out / "smoke_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(f"wrote {a.out / 'smoke_report.json'}")


if __name__ == "__main__":
    main()
