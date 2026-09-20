"""ConnectomeNet: the MaleCNS wiring diagram as a frozen-topology recurrent network.

Frozen: which neuron talks to which (src -> dst) and the sign of every edge (Dale's law, from the
presynaptic neuron's neurotransmitter). Learnable:

  theta_e        per-edge gain magnitude, g_e = softplus(theta_e) * exp(log_scale); initialised so that
                 g_e = log1p(synapse count) with the global scale at 1
  bias_i         per-neuron bias
  leak_i         a_i = sigmoid(leak_logit_i), initialised 0.5
  homeo_gain_i   per-neuron homeostatic gain, initialised 1
  W_in           Linear(F -> n_sensory): input features drive the sensory neurons only
  readout        Linear(n_descending + n_motor -> sum of head dims)

Dynamics, hidden state h [N, B] (neurons x batch, so edge gathers read contiguous rows):

  h_0 = 0
  for t in 1..T:
      agg  = sum_{e: dst_e = i} sign_e * g_e * h[src_e]              (deterministic segment sum, edgeops)
      pre  = agg * norm_i + bias_i
      pre[sensory] += W_in x + b_in
      h    = (1 - a_i) * h + a_i * relu(homeo_gain_i * pre)

Normalisation choice (norm_i is a fixed per-neuron constant, so it adds no degree of freedom):

  norm="total_gain" (default)  norm_i = 1 / sum_{e: dst_e = i} log1p(syn_e), i.e. the reciprocal of the
      neuron's total incoming gain at initialisation. At init every neuron's pre-activation is then a signed
      weighted average of its inputs, |pre_i| <= max|h|, so with relu and a leak in (0,1) the activity is
      bounded by the sensory drive for any T. The learnable homeostatic gain and the per-edge gains can grow
      from there during training.
  norm="sqrt_degree"           norm_i = 1 / sqrt(max(in_degree_i, 1)). Variance-preserving only for zero-mean
      inputs. The connectome is 62.8% excitatory by edge, so the expected input to a neuron is roughly
      0.64 * mean(g) * sqrt(in_degree) * h and hubs amplify several-fold per step. Measured on the 2,000
      highest-degree neurons at init (tests/test_model.py): hidden norm 4.0 after step 1 -> 1.4e6 after
      step 8. Kept as an option for ablation only.
  Mean aggregation (1/in_degree) was not used: it discards the count of inputs, which is anatomical
  information, and still amplifies (expected ratio ~0.64 * mean(g) ~ 1.6 per step).

Readout heads are linear; regression targets are expected scaled to 0-1 by the data adapter.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F_

from .edgeops import EdgeLayout, signed_aggregate
from .graph import Graph


@dataclass(frozen=True)
class Head:
    name: str
    kind: str           # "regression" | "classification"
    dim: int
    classes: tuple = ()


@dataclass(frozen=True)
class OutputSpec:
    heads: tuple

    @classmethod
    def build(cls, items) -> "OutputSpec":
        heads = []
        for name, kind, d in items:
            if kind == "classification":
                classes = tuple(d)
                heads.append(Head(name, kind, len(classes), classes))
            elif kind == "regression":
                heads.append(Head(name, kind, int(d)))
            else:
                raise ValueError(kind)
        return cls(tuple(heads))

    @property
    def total_dim(self) -> int:
        return sum(h.dim for h in self.heads)

    @property
    def classes(self) -> dict:
        return {h.name: list(h.classes) for h in self.heads if h.kind == "classification"}

    def split(self, y: torch.Tensor) -> dict:
        out, off = {}, 0
        for h in self.heads:
            out[h.name] = y[:, off:off + h.dim]
            off += h.dim
        return out


TIERS = ["BELOW THRESHOLD", "BRONZE", "SILVER", "GOLD", "PLATINUM"]
GATES = ["COLLAPSE", "ALERT", "HOLD", "PASS"]
DTI_SPEC = OutputSpec.build([("dims", "regression", 8), ("composite", "regression", 1), ("tier", "classification", TIERS)])
BII_SPEC = OutputSpec.build([("bii", "regression", 1), ("gate", "classification", GATES)])
SPECS = {"dti": DTI_SPEC, "bii": BII_SPEC}


def _softplus_inverse(y: torch.Tensor) -> torch.Tensor:
    return y + torch.log(-torch.expm1(-y))   # log(exp(y) - 1), stable for y > 0


def count_parameters(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters() if p.requires_grad)


class ConnectomeNet(nn.Module):
    arm = "connectome"

    def __init__(self, graph: Graph, in_dim: int, spec: OutputSpec, T: int = 8, device="cpu", norm: str = "total_gain"):
        super().__init__()
        self.norm = norm
        device = torch.device(device)
        self.graph_summary = graph.summary()
        self.n, self.e, self.T, self.in_dim, self.spec = graph.n, graph.e, int(T), int(in_dim), spec
        self.layout = EdgeLayout(graph.n, graph.src, graph.dst, device)

        # frozen topology / sign / normalisation
        self.register_buffer("sign", torch.from_numpy(graph.sign.astype(np.float32)))
        if norm == "total_gain":
            total = np.bincount(graph.dst, weights=graph.gain_init(), minlength=graph.n)
            inv_norm = 1.0 / np.where(total > 0, total, 1.0)
        elif norm == "sqrt_degree":
            inv_norm = 1.0 / np.sqrt(np.maximum(graph.in_degree(), 1))
        else:
            raise ValueError(f"unknown norm {norm!r}")
        self.register_buffer("inv_norm", torch.from_numpy(inv_norm.astype(np.float32)))
        self.register_buffer("sensory_idx", torch.from_numpy(np.flatnonzero(graph.sensory_mask)))
        self.register_buffer("readout_idx", torch.from_numpy(np.flatnonzero(graph.readout_mask)))
        if len(self.sensory_idx) == 0 or len(self.readout_idx) == 0:
            raise ValueError("graph needs at least one sensory and one descending/motor neuron")

        # learnable
        self.theta = nn.Parameter(_softplus_inverse(torch.from_numpy(graph.gain_init())))
        self.log_scale = nn.Parameter(torch.zeros(()))
        self.bias = nn.Parameter(torch.zeros(graph.n))
        self.leak_logit = nn.Parameter(torch.zeros(graph.n))          # sigmoid(0) = 0.5
        self.homeo_gain = nn.Parameter(torch.ones(graph.n))
        self.w_in = nn.Linear(in_dim, len(self.sensory_idx))
        self.readout = nn.Linear(len(self.readout_idx), spec.total_dim)
        self.to(device)
        self.device = device

    # ---- pieces -------------------------------------------------------
    def edge_gain(self) -> torch.Tensor:
        return F_.softplus(self.theta) * torch.exp(self.log_scale)

    def leak(self) -> torch.Tensor:
        return torch.sigmoid(self.leak_logit)

    def parameter_breakdown(self) -> dict:
        return {name: p.numel() for name, p in self.named_parameters() if p.requires_grad}

    def _step_inputs(self, x: torch.Tensor):
        w = self.sign * self.edge_gain()                    # [E]
        a = self.leak()[:, None]                            # [N,1]
        drive = self.w_in(x).t()                            # [n_sensory, B]
        return w, a, drive

    def _step(self, h, w, a, drive):
        agg = signed_aggregate(h, w, self.layout)           # [N,B]
        pre = agg * self.inv_norm[:, None] + self.bias[:, None]
        pre = pre.index_add(0, self.sensory_idx, drive)     # unique indices: one add per row
        return (1 - a) * h + a * torch.relu(self.homeo_gain[:, None] * pre)

    def hidden_trajectory(self, x: torch.Tensor) -> list:
        w, a, drive = self._step_inputs(x)
        h = x.new_zeros(self.n, x.shape[0])
        hs = [h]
        for _ in range(self.T):
            h = self._step(h, w, a, drive)
            hs.append(h)
        return hs

    def forward(self, x: torch.Tensor) -> dict:
        w, a, drive = self._step_inputs(x)
        h = x.new_zeros(self.n, x.shape[0])
        for _ in range(self.T):
            h = self._step(h, w, a, drive)
        ro = h.index_select(0, self.readout_idx).t()        # [B, n_readout]
        return self.spec.split(self.readout(ro))


def describe(model: nn.Module) -> str:
    total = count_parameters(model)
    lines = [f"{model.__class__.__name__}: {total:,} trainable parameters"]
    if hasattr(model, "parameter_breakdown"):
        for k, v in model.parameter_breakdown().items():
            lines.append(f"  {k:<16} {v:>12,}")
    return "\n".join(lines)
