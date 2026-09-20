"""Metrics for the heads. Regression MAE is reported in 0-100 units (targets are scaled 0-1)."""

from __future__ import annotations

import torch

from .model import OutputSpec


def mae_per_dim(pred: torch.Tensor, y: torch.Tensor, scale: float = 100.0) -> list:
    return ((pred - y).abs().mean(0) * scale).tolist()


def accuracy(logits: torch.Tensor, y: torch.Tensor) -> float:
    return (logits.argmax(1) == y).float().mean().item()


def macro_f1(logits: torch.Tensor, y: torch.Tensor, n_classes: int) -> float:
    pred = logits.argmax(1)
    f1s = []
    for c in range(n_classes):
        tp = ((pred == c) & (y == c)).sum().item()
        fp = ((pred == c) & (y != c)).sum().item()
        fn = ((pred != c) & (y == c)).sum().item()
        denom = 2 * tp + fp + fn
        f1s.append(2 * tp / denom if denom else 0.0)   # class absent in both pred and truth counts as 0
    return sum(f1s) / n_classes


def head_metrics(spec: OutputSpec, out: dict, Y: dict) -> dict:
    m = {}
    for h in spec.heads:
        p, y = out[h.name], Y[h.name]
        if h.kind == "regression":
            per = mae_per_dim(p, y)
            m[f"{h.name}_mae"] = per if h.dim > 1 else per[0]
            if h.dim > 1:
                m[f"{h.name}_mae_mean"] = sum(per) / len(per)
        else:
            m[f"{h.name}_acc"] = accuracy(p, y)
            m[f"{h.name}_macro_f1"] = macro_f1(p, y, h.dim)
    return m


def loss_terms(spec: OutputSpec, out: dict, Y: dict) -> dict:
    terms = {}
    for h in spec.heads:
        if h.kind == "regression":
            terms[h.name] = torch.nn.functional.mse_loss(out[h.name], Y[h.name])
        else:
            terms[h.name] = torch.nn.functional.cross_entropy(out[h.name], Y[h.name])
    return terms


def macro_f1_supported(logits: torch.Tensor, y: torch.Tensor, n_classes: int, min_support: int = 30) -> dict:
    """Macro-F1 over classes whose TRUE support is >= min_support (protocol section 7); lists the classes used."""
    pred = logits.argmax(1)
    used, f1s = [], []
    for c in range(n_classes):
        support = int((y == c).sum().item())
        if support < min_support:
            continue
        tp = ((pred == c) & (y == c)).sum().item()
        fp = ((pred == c) & (y != c)).sum().item()
        fn = ((pred != c) & (y == c)).sum().item()
        denom = 2 * tp + fp + fn
        f1s.append(2 * tp / denom if denom else 0.0)
        used.append(c)
    return {"macro_f1": sum(f1s) / len(f1s) if f1s else float("nan"), "classes_used": used, "min_support": min_support}


def calibration(logits: torch.Tensor, y: torch.Tensor, n_classes: int, n_bins: int = 10) -> dict:
    """Expected calibration error of the top-class probability over n_bins equal-mass bins, plus the multiclass
    Brier score (mean squared error between the probability vector and the one-hot truth)."""
    p = torch.softmax(logits.float(), 1)
    conf, pred = p.max(1)
    correct = (pred == y).float()
    order = conf.argsort()
    bins = torch.tensor_split(order, n_bins)
    ece = 0.0
    n = len(y)
    for b in bins:
        if len(b) == 0:
            continue
        ece += (len(b) / n) * abs(conf[b].mean().item() - correct[b].mean().item())
    onehot = torch.nn.functional.one_hot(y, n_classes).float()
    brier = ((p - onehot) ** 2).sum(1).mean().item()
    return {"ece": ece, "brier": brier, "n_bins": n_bins, "mean_confidence": conf.mean().item(), "accuracy": correct.mean().item()}
