"""Forward latency and throughput of the FULL-graph ConnectomeNet at T=8 (numbers for the paper's cost table).

  .venv/bin/python -m flytrust.bench_speed [--device mps] [--in-dim 64] [--T 8] [--out runs/bench_speed.json]

Reports, per batch size (1 and 256): median forward latency per batch, latency per record, records/sec, and
device memory (MPS driver-allocated) plus process peak RSS. Also times one training step (forward + backward +
AdamW) at batch 64, which is what sets epoch time. Every number is measured here; nothing is estimated.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import torch

from .graph import load_graph, ROOT
from .model import ConnectomeNet, DTI_SPEC, count_parameters
from .train import peak_rss_bytes, device_mem_bytes


def _sync(device):
    if device.type == "mps":
        torch.mps.synchronize()


def time_forward(model, x, reps, device):
    with torch.no_grad():
        model(x); _sync(device)                       # warm-up
        ts = []
        for _ in range(reps):
            t0 = time.perf_counter(); model(x); _sync(device)
            ts.append(time.perf_counter() - t0)
    return ts


def time_train_step(model, x, reps, device):
    opt = torch.optim.AdamW(model.parameters(), lr=1e-4)
    ts = []
    for i in range(reps + 1):
        t0 = time.perf_counter()
        out = model(x)
        loss = sum(o.pow(2).mean() for o in out.values())
        opt.zero_grad(set_to_none=True); loss.backward(); opt.step(); _sync(device)
        if i:
            ts.append(time.perf_counter() - t0)
    return ts


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    ap.add_argument("--in-dim", type=int, default=64)
    ap.add_argument("--T", type=int, default=8)
    ap.add_argument("--batches", type=int, nargs="+", default=[1, 256])
    ap.add_argument("--train-batch", type=int, default=64)
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "bench_speed.json")
    a = ap.parse_args(argv)
    device = torch.device(a.device)
    torch.manual_seed(0)
    g = load_graph()
    t0 = time.perf_counter()
    model = ConnectomeNet(g, a.in_dim, DTI_SPEC, T=a.T, device=device)
    build_s = time.perf_counter() - t0
    res = {"device": str(device), "T": a.T, "in_dim": a.in_dim, "graph": g.summary(),
           "trainable_params": count_parameters(model), "padded_edges": model.layout.padded_edges,
           "build_seconds": build_s, "torch": torch.__version__, "forward": {}, "train_step": {}}
    for B in a.batches:
        x = torch.randn(B, a.in_dim, device=device)
        ts = time_forward(model, x, reps=20 if B <= 16 else 5, device=device)
        med = statistics.median(ts)
        res["forward"][str(B)] = {"batch": B, "median_latency_s": med, "min_latency_s": min(ts),
                                  "latency_per_record_ms": 1000 * med / B, "records_per_sec": B / med,
                                  "device_bytes_after": device_mem_bytes(device), "peak_rss_bytes": peak_rss_bytes()}
        print(f"forward B={B:>4}: {1000 * med:9.1f} ms/batch  {1000 * med / B:8.3f} ms/record  "
              f"{B / med:9.1f} rec/s  dev {device_mem_bytes(device) / 1e9:.2f} GB  rss {peak_rss_bytes() / 1e9:.2f} GB")
    B = a.train_batch
    x = torch.randn(B, a.in_dim, device=device)
    ts = time_train_step(model, x, reps=3, device=device)
    med = statistics.median(ts)
    res["train_step"][str(B)] = {"batch": B, "median_step_s": med, "records_per_sec": B / med,
                                 "device_bytes_after": device_mem_bytes(device), "peak_rss_bytes": peak_rss_bytes()}
    print(f"train step B={B}: {med:.3f} s/step  {B / med:.1f} rec/s  dev {device_mem_bytes(device) / 1e9:.2f} GB  "
          f"rss {peak_rss_bytes() / 1e9:.2f} GB")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=2) + "\n")
    print(f"wrote {a.out}")
    return res


if __name__ == "__main__":
    main()
