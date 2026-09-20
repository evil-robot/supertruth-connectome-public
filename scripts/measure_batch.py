"""Measure once: train-step throughput at B=64 vs B=128 on the full graph with the real DTI input width (65).

Writes runs/batch_choice.json. The pilot uses 128 only if it is at least 5% faster per record AND peak device memory stays
under the cap; otherwise 64. Run before scripts/run_arm.py; run_arm reads the choice.

  .venv/bin/python scripts/measure_batch.py [--cap-gb 44]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flytrust.graph import load_graph, ROOT                    # noqa: E402
from flytrust.metrics import loss_terms                        # noqa: E402
from flytrust.model import ConnectomeNet, DTI_SPEC             # noqa: E402
from flytrust.train import device_mem_bytes                    # noqa: E402


def measure(graph, batch: int, device: str, steps: int = 3, T: int = 8, in_dim: int = 65) -> dict:
    torch.manual_seed(0)
    model = ConnectomeNet(graph, in_dim, DTI_SPEC, T=T, device=device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    x = torch.randn(batch, in_dim, device=device)
    y = {"dims": torch.rand(batch, 8, device=device), "composite": torch.rand(batch, 1, device=device),
         "tier": torch.randint(0, 5, (batch,), device=device)}
    times, peak = [], 0
    for i in range(steps + 1):
        if device == "mps":
            torch.mps.synchronize()
        t0 = time.perf_counter()
        out = model(x); loss = sum(loss_terms(DTI_SPEC, out, y).values())
        opt.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step()
        if device == "mps":
            torch.mps.synchronize()
        dt = time.perf_counter() - t0
        peak = max(peak, device_mem_bytes(torch.device(device)))
        if i > 0:
            times.append(dt)
    del model, opt
    if device == "mps":
        torch.mps.empty_cache()
    med = sorted(times)[len(times) // 2]
    return {"batch": batch, "median_step_s": med, "records_per_sec": batch / med, "peak_device_bytes": peak}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    ap.add_argument("--cap-gb", type=float, default=44.0)
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "batch_choice.json")
    a = ap.parse_args()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    graph = load_graph()
    res = {str(b): measure(graph, b, a.device) for b in (64, 128)}
    for b, r in res.items():
        print(f"B={b}: {r['median_step_s']:.3f} s/step, {r['records_per_sec']:.1f} rec/s, peak dev {r['peak_device_bytes'] / 1e9:.1f} GB")
    faster = res["128"]["records_per_sec"] > 1.05 * res["64"]["records_per_sec"]   # a real gain, not noise
    fits = res["128"]["peak_device_bytes"] < a.cap_gb * 1e9
    choice = 128 if (faster and fits) else 64
    doc = {"device": a.device, "in_dim": 65, "T": 8, "measured": res, "cap_gb": a.cap_gb,
           "b128_faster_per_record": faster, "b128_under_cap": fits, "choice": choice,
           "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    a.out.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"choice: B={choice} -> {a.out}")


if __name__ == "__main__":
    main()
