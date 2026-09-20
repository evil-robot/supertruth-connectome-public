"""Generic trainer for every arm.

  .venv/bin/python -m flytrust.train --data D.npz --splits S.npz --spec dti --arm connectome \
      --epochs 10 --batch 64 --T 8 --lr 1e-3 --seed 0 --device mps --out runs/NAME [--graph-k K]

Splits come from a file (never made here). Losses: MSE on 0-1 scaled regressions + CE on class heads.
Per epoch: MAE per dimension (0-100 units), composite MAE, tier accuracy + macro-F1, a determinism check
(two forward passes on the same input must be bitwise identical), wall time, sampled peak memory.
Checkpoints: best.safetensors + run.json (every hyperparameter, git SHA, graph_meta sha256, arm name).
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import resource
import subprocess
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

import numpy as np
import torch
from safetensors.torch import save_file

from .controls import build_arm, RidgeReadout, ARMS
from .data_adapters import load_npz_dataset, load_splits, SPEC_BY_NAME
from .graph import load_graph, ROOT
from .metrics import head_metrics, loss_terms
from .model import OutputSpec, count_parameters, describe


@dataclass
class TrainConfig:
    epochs: int = 10
    batch_size: int = 64
    lr: float = 1e-3
    weight_decay: float = 0.01
    grad_clip: float = 1.0
    warmup_steps: int = 0
    patience: int = 3                  # early stopping on validation loss (epochs)
    seed: int = 0
    device: str = "mps"
    T: int = 8
    arm: str = "connectome"
    spec: str = "dti"
    graph_k: int = 0                    # 0 = FULL graph; >0 = subgraph (smoke tests only; recorded in run.json)
    norm: str = "total_gain"
    ridge_lambda: float = 1.0
    determinism_check: bool = True
    extra: dict = field(default_factory=dict)


def git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


def peak_rss_bytes() -> int:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(r if platform.system() == "Darwin" else r * 1024)


def device_mem_bytes(device: torch.device) -> int:
    if device.type == "mps":
        return int(torch.mps.driver_allocated_memory())
    return 0


def seed_all(seed: int):
    torch.manual_seed(seed)
    np.random.seed(seed)


class Trainer:
    def __init__(self, model, spec: OutputSpec, X: torch.Tensor, Y: dict, train_idx: np.ndarray,
                 val_idx: np.ndarray, cfg: TrainConfig, out_dir: Path, run_meta: dict | None = None,
                 log=print):
        self.model, self.spec, self.cfg, self.log = model, spec, cfg, log
        self.device = torch.device(cfg.device)
        self.X, self.Y = X, Y
        self.train_idx = torch.as_tensor(train_idx, dtype=torch.long)
        self.val_idx = torch.as_tensor(val_idx, dtype=torch.long)
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.run_meta = run_meta or {}
        self.history = []
        self.peak_dev = 0

    # ---- helpers ------------------------------------------------------
    def _batch(self, idx):
        x = self.X[idx].to(self.device)
        y = {k: v[idx].to(self.device) for k, v in self.Y.items()}
        return x, y

    def _sample_mem(self):
        self.peak_dev = max(self.peak_dev, device_mem_bytes(self.device))

    @torch.no_grad()
    def evaluate(self, idx: torch.Tensor, batch_size: int | None = None) -> dict:
        self.model.eval()
        bs = batch_size or self.cfg.batch_size
        outs = {h.name: [] for h in self.spec.heads}
        total, n = 0.0, 0
        for s in range(0, len(idx), bs):
            x, y = self._batch(idx[s:s + bs])
            out = self.model(x)
            lt = loss_terms(self.spec, out, y)
            total += sum(v.item() for v in lt.values()) * len(x)
            n += len(x)
            for k in outs:
                outs[k].append(out[k].float().cpu())
        outs = {k: torch.cat(v) for k, v in outs.items()}
        ys = {k: v[idx] for k, v in self.Y.items()}
        m = head_metrics(self.spec, outs, ys)
        m["loss"] = total / max(n, 1)
        return m

    @torch.no_grad()
    def determinism_check(self) -> bool:
        self.model.eval()
        idx = self.val_idx[: min(8, len(self.val_idx))]
        x, _ = self._batch(idx)
        a, b = self.model(x), self.model(x)
        same = all(torch.equal(a[k], b[k]) for k in a)
        if not same:
            diffs = {k: (a[k] - b[k]).abs().max().item() for k in a}
            raise AssertionError(f"forward pass is not deterministic on {self.device}: max diffs {diffs}")
        return True

    # ---- gradient training ------------------------------------------
    def fit(self) -> dict:
        cfg = self.cfg
        seed_all(cfg.seed)
        params = [p for p in self.model.parameters() if p.requires_grad]
        opt = torch.optim.AdamW(params, lr=cfg.lr, weight_decay=cfg.weight_decay)
        steps_per_epoch = math.ceil(len(self.train_idx) / cfg.batch_size)
        total_steps = max(1, steps_per_epoch * cfg.epochs)

        def lr_at(step):
            if step < cfg.warmup_steps:
                return (step + 1) / cfg.warmup_steps
            p = (step - cfg.warmup_steps) / max(1, total_steps - cfg.warmup_steps)
            return 0.5 * (1 + math.cos(math.pi * min(1.0, p)))

        sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_at)
        gen = torch.Generator().manual_seed(cfg.seed)
        best, best_epoch, bad = float("inf"), -1, 0
        step = 0
        for epoch in range(cfg.epochs):
            self.model.train()
            t0 = time.perf_counter()
            perm = self.train_idx[torch.randperm(len(self.train_idx), generator=gen)]
            tr_loss, tr_n = 0.0, 0
            first_loss = None
            for s in range(0, len(perm), cfg.batch_size):
                x, y = self._batch(perm[s:s + cfg.batch_size])
                out = self.model(x)
                lt = loss_terms(self.spec, out, y)
                loss = sum(lt.values())
                if not torch.isfinite(loss):
                    raise FloatingPointError(f"non-finite loss at epoch {epoch} step {step}")
                opt.zero_grad(set_to_none=True)
                loss.backward()
                gn = torch.nn.utils.clip_grad_norm_(params, cfg.grad_clip)
                opt.step()
                sched.step()
                step += 1
                li = loss.item()
                first_loss = li if first_loss is None else first_loss
                tr_loss += li * len(x)
                tr_n += len(x)
                self._sample_mem()
            if self.device.type == "mps":
                torch.mps.synchronize()
            train_time = time.perf_counter() - t0
            val = self.evaluate(self.val_idx)
            det = self.determinism_check() if cfg.determinism_check else None
            rec = {"epoch": epoch, "train_loss": tr_loss / max(tr_n, 1), "train_first_batch_loss": first_loss,
                   "val": val, "deterministic": det, "epoch_train_seconds": train_time,
                   "epoch_total_seconds": time.perf_counter() - t0, "lr": sched.get_last_lr()[0],
                   "last_grad_norm": float(gn), "peak_rss_bytes": peak_rss_bytes(),
                   "peak_device_bytes_sampled": self.peak_dev}
            self.history.append(rec)
            self.log(f"epoch {epoch}: train {rec['train_loss']:.4f} val {val['loss']:.4f} "
                     f"{self._fmt_val(val)} det={det} {train_time:.1f}s "
                     f"rss {peak_rss_bytes() / 1e9:.2f}GB dev {self.peak_dev / 1e9:.2f}GB")
            if val["loss"] < best - 1e-6:
                best, best_epoch, bad = val["loss"], epoch, 0
                self.save_checkpoint("best")
            else:
                bad += 1
                if bad >= cfg.patience:
                    self.log(f"early stop at epoch {epoch} (best epoch {best_epoch})")
                    break
            self.write_run_json(best_epoch=best_epoch, best_val_loss=best)
        self.write_run_json(best_epoch=best_epoch, best_val_loss=best, finished=True)
        return {"history": self.history, "best_epoch": best_epoch, "best_val_loss": best}

    # ---- closed-form arm ---------------------------------------------
    def fit_closed_form(self) -> dict:
        t0 = time.perf_counter()
        x, y = self._batch(self.train_idx)
        self.model.fit(x, y)
        val = self.evaluate(self.val_idx)
        det = self.determinism_check() if self.cfg.determinism_check else None
        rec = {"epoch": 0, "train_loss": self.evaluate(self.train_idx)["loss"], "val": val, "deterministic": det,
               "epoch_total_seconds": time.perf_counter() - t0, "peak_rss_bytes": peak_rss_bytes()}
        self.history.append(rec)
        self.log(f"ridge: val {val['loss']:.4f} {self._fmt_val(val)}")
        self.save_checkpoint("best")
        self.write_run_json(best_epoch=0, best_val_loss=val["loss"], finished=True)
        return {"history": self.history, "best_epoch": 0, "best_val_loss": val["loss"]}

    def _fmt_val(self, val: dict) -> str:
        bits = []
        for k, v in val.items():
            if k == "loss":
                continue
            bits.append(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={[round(t, 2) for t in v]}")
        return " ".join(bits)

    # ---- persistence -------------------------------------------------
    def save_checkpoint(self, tag: str):
        sd = {k: v.detach().cpu().contiguous() for k, v in self.model.state_dict().items()}
        save_file(sd, str(self.out_dir / f"{tag}.safetensors"))

    def write_run_json(self, **extra):
        meta = {
            "arm": self.cfg.arm,
            "config": asdict(self.cfg),
            "git_sha": git_sha(),
            "graph_meta_sha256": self.run_meta.get("graph", {}).get("meta_sha256"),
            "run_meta": self.run_meta,
            "trainable_params": count_parameters(self.model),
            "param_breakdown": self.model.parameter_breakdown() if hasattr(self.model, "parameter_breakdown") else None,
            "n_train": int(len(self.train_idx)), "n_val": int(len(self.val_idx)),
            "torch": torch.__version__, "python": sys.version.split()[0], "platform": platform.platform(),
            "history": self.history,
        }
        meta.update(extra)
        (self.out_dir / "run.json").write_text(json.dumps(meta, indent=2, default=str) + "\n")


def run(cfg: TrainConfig, data: Path, splits: Path, out: Path, graph=None, log=print):
    spec = SPEC_BY_NAME[cfg.spec]
    X, Y = load_npz_dataset(data, spec)
    tr, va = load_splits(splits)
    if graph is None:
        graph = load_graph()
        if cfg.graph_k:
            graph = graph.subgraph(cfg.graph_k, seed=cfg.seed)
            log(f"WARNING: subgraph of {cfg.graph_k} neurons (smoke test only, recorded in run.json)")
    seed_all(cfg.seed)
    kw = {"norm": cfg.norm} if cfg.arm in ("connectome", "shuffle", "er") else {}
    if cfg.arm == "ridge":
        kw = {"lam": cfg.ridge_lambda}
    model, meta = build_arm(cfg.arm, graph, X.shape[1], spec, T=cfg.T, device=cfg.device, seed=cfg.seed, **kw)
    meta["data"] = str(data); meta["splits"] = str(splits)
    log(describe(model))
    trainer = Trainer(model, spec, X, Y, tr, va, cfg, out, run_meta=meta, log=log)
    if isinstance(model, RidgeReadout):
        return trainer.fit_closed_form(), trainer
    return trainer.fit(), trainer


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--splits", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--spec", choices=list(SPEC_BY_NAME), default="dti")
    ap.add_argument("--arm", choices=ARMS, default="connectome")
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--weight-decay", type=float, default=0.01)
    ap.add_argument("--grad-clip", type=float, default=1.0)
    ap.add_argument("--warmup-steps", type=int, default=0)
    ap.add_argument("--patience", type=int, default=3)
    ap.add_argument("--T", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    ap.add_argument("--graph-k", type=int, default=0, help="0 = full graph; >0 = subgraph for smoke tests")
    ap.add_argument("--norm", default="total_gain", choices=["total_gain", "sqrt_degree"])
    ap.add_argument("--ridge-lambda", type=float, default=1.0)
    a = ap.parse_args(argv)
    cfg = TrainConfig(epochs=a.epochs, batch_size=a.batch, lr=a.lr, weight_decay=a.weight_decay,
                      grad_clip=a.grad_clip, warmup_steps=a.warmup_steps, patience=a.patience, seed=a.seed,
                      device=a.device, T=a.T, arm=a.arm, spec=a.spec, graph_k=a.graph_k, norm=a.norm,
                      ridge_lambda=a.ridge_lambda)
    run(cfg, a.data, a.splits, a.out)


if __name__ == "__main__":
    main()
