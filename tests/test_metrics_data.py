import numpy as np
import torch

from flytrust.metrics import macro_f1, accuracy, mae_per_dim, head_metrics, loss_terms
from flytrust.data_adapters import synthetic_dataset, save_npz_dataset, load_npz_dataset, make_splits, load_splits
from flytrust.model import DTI_SPEC, BII_SPEC


def test_macro_f1_and_accuracy():
    y = torch.tensor([0, 0, 1, 1, 2])
    logits = torch.nn.functional.one_hot(torch.tensor([0, 1, 1, 1, 0]), 3).float()
    assert abs(accuracy(logits, y) - 0.6) < 1e-6
    # class0: tp1 fp1 fn1 -> f1 .5 ; class1: tp2 fp1 fn0 -> .8 ; class2: 0
    assert abs(macro_f1(logits, y, 3) - (0.5 + 0.8 + 0.0) / 3) < 1e-6


def test_mae_in_0_100_units():
    p = torch.tensor([[0.5, 0.2]]); y = torch.tensor([[0.4, 0.2]])
    assert np.allclose(mae_per_dim(p, y), [10.0, 0.0], atol=1e-4)


def test_head_metrics_and_losses_keys():
    X, Y = synthetic_dataset(64, 8, DTI_SPEC, seed=0)
    out = {"dims": torch.zeros(64, 8), "composite": torch.zeros(64, 1), "tier": torch.zeros(64, 5)}
    m = head_metrics(DTI_SPEC, out, Y)
    assert len(m["dims_mae"]) == 8 and "composite_mae" in m and "tier_acc" in m and "tier_macro_f1" in m
    lt = loss_terms(DTI_SPEC, out, Y)
    assert set(lt) == {"dims", "composite", "tier"} and all(torch.isfinite(v) for v in lt.values())


def test_synthetic_roundtrip_and_splits(tmp_path):
    X, Y = synthetic_dataset(200, 16, BII_SPEC, seed=1)
    X2, Y2 = synthetic_dataset(200, 16, BII_SPEC, seed=1)
    assert torch.equal(X, X2) and torch.equal(Y["gate"], Y2["gate"])
    assert Y["bii"].shape == (200, 1) and Y["gate"].max() == 3 and Y["gate"].min() == 0
    assert 0 <= Y["bii"].min() and Y["bii"].max() <= 1
    p = tmp_path / "d.npz"
    save_npz_dataset(p, X, Y)
    X3, Y3 = load_npz_dataset(p, BII_SPEC)
    assert torch.equal(X3, X) and torch.equal(Y3["gate"], Y["gate"])
    tr, va = make_splits(tmp_path / "s.npz", 200, 0.2, seed=0)
    assert len(tr) == 160 and len(va) == 40 and not len(np.intersect1d(tr, va))
    tr2, va2 = load_splits(tmp_path / "s.npz")
    assert np.array_equal(tr, tr2)
