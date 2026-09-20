import json

import numpy as np
import torch
from safetensors.torch import load_file

from flytrust.data_adapters import synthetic_dataset, save_npz_dataset, make_splits
from flytrust.train import TrainConfig, run


def _dataset(tmp_path, spec, n=256, F=8):
    from flytrust.data_adapters import SPEC_BY_NAME
    X, Y = synthetic_dataset(n, F, SPEC_BY_NAME[spec], seed=0)
    d = tmp_path / "d.npz"; s = tmp_path / "s.npz"
    save_npz_dataset(d, X, Y)
    make_splits(s, n, 0.25, seed=0)
    return d, s


def test_connectome_trains_and_writes_artifacts(tmp_path, small_graph):
    d, s = _dataset(tmp_path, "dti")
    cfg = TrainConfig(epochs=3, batch_size=32, lr=3e-3, device="cpu", T=3, arm="connectome", spec="dti",
                      graph_k=2000, patience=10, seed=0)
    res, trainer = run(cfg, d, s, tmp_path / "run", graph=small_graph, log=lambda *a: None)
    hist = res["history"]
    assert len(hist) == 3
    assert hist[-1]["train_loss"] < hist[0]["train_first_batch_loss"]
    for rec in hist:
        assert rec["deterministic"] is True
        assert rec["epoch_train_seconds"] > 0 and rec["peak_rss_bytes"] > 0
        v = rec["val"]
        assert len(v["dims_mae"]) == 8 and "composite_mae" in v and "tier_acc" in v and "tier_macro_f1" in v
    rj = json.loads((tmp_path / "run" / "run.json").read_text())
    assert rj["arm"] == "connectome" and rj["config"]["seed"] == 0 and rj["config"]["graph_k"] == 2000
    assert rj["graph_meta_sha256"] == small_graph.meta_sha256 and len(rj["graph_meta_sha256"]) == 64
    assert "git_sha" in rj and rj["finished"] is True and rj["trainable_params"] == sum(rj["param_breakdown"].values())
    sd = load_file(str(tmp_path / "run" / "best.safetensors"))
    assert sd["theta"].shape == (small_graph.e,)


def test_seed_reproducibility(tmp_path, small_graph):
    d, s = _dataset(tmp_path, "bii", n=128)
    outs = []
    for i in range(2):
        cfg = TrainConfig(epochs=1, batch_size=32, device="cpu", T=2, arm="connectome", spec="bii", graph_k=2000, seed=7)
        res, _ = run(cfg, d, s, tmp_path / f"r{i}", graph=small_graph, log=lambda *a: None)
        outs.append(res["history"][0]["train_loss"])
    assert outs[0] == outs[1]


def test_ridge_and_mlp_arms(tmp_path, small_graph):
    d, s = _dataset(tmp_path, "bii", n=200)
    cfg = TrainConfig(epochs=1, device="cpu", T=2, arm="ridge", spec="bii", graph_k=2000)
    res, _ = run(cfg, d, s, tmp_path / "ridge", graph=small_graph, log=lambda *a: None)
    assert res["history"][0]["deterministic"] is True and "gate_acc" in res["history"][0]["val"]
    cfg = TrainConfig(epochs=2, batch_size=50, device="cpu", T=2, arm="mlp", spec="bii", graph_k=2000, patience=5)
    res, tr = run(cfg, d, s, tmp_path / "mlp", graph=small_graph, log=lambda *a: None)
    rj = json.loads((tmp_path / "mlp" / "run.json").read_text())
    assert abs(rj["trainable_params"] - rj["run_meta"]["target_params"]) / rj["run_meta"]["target_params"] <= 0.02


def test_early_stopping(tmp_path, small_graph):
    d, s = _dataset(tmp_path, "bii", n=96)
    cfg = TrainConfig(epochs=20, batch_size=48, lr=0.0, device="cpu", T=2, arm="mlp", spec="bii", graph_k=2000, patience=2)
    res, _ = run(cfg, d, s, tmp_path / "es", graph=small_graph, log=lambda *a: None)
    assert len(res["history"]) == 3      # lr=0 -> no improvement after epoch 0 -> stop after 2 bad epochs
