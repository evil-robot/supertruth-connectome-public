"""Deterministic signed aggregation over an edge list, for CPU and MPS.

out[j] = sum over edges e with dst_e == j of  w_e * h[src_e]

Why not torch.sparse or index_add_: torch sparse ops are unreliable on MPS, and index_add_ / scatter_add_ on
MPS use atomic float adds, so the same input gives different bits on every call (measured max |diff| ~1e-4 on
the full graph). The paper's trainer asserts bitwise determinism of the forward pass, so the scatter is done
as a padded segment sum instead:

  * edges are permuted into dst-sorted order and grouped into buckets by in-degree; bucket b holds every
    postsynaptic neuron whose in-degree d satisfies 2^(b-1) < d <= 2^b and pads each neuron's edge list to
    width 2^b with a dummy edge (src = N, a zero row; w = 0).  Padding is < 2x the edge count.
  * per bucket: gather h_pad[src_pad] * w_pad  -> view(n_b, 2^b, B).sum(1)  -> write rows (unique indices).
    Reductions over a fixed view have a fixed order, so the forward is bitwise reproducible.

The autograd Function saves only h [N,B] and w [E]; the [E,B] gathered tensor is transient in both forward and
backward, so activation memory does not scale with T x E x B. The backward's grad wrt h uses index_add_ (atomic
on MPS), so gradients are deterministic only up to float reordering; the forward is exact.
"""

from __future__ import annotations

import numpy as np
import torch


class EdgeLayout:
    """Precomputed padded, bucketed edge ordering for a fixed (src, dst) topology on one device."""

    def __init__(self, n: int, src: np.ndarray, dst: np.ndarray, device: torch.device):
        src = np.asarray(src, dtype=np.int64)
        dst = np.asarray(dst, dtype=np.int64)
        e = len(src)
        self.n, self.e, self.device = int(n), int(e), torch.device(device)
        indeg = np.bincount(dst, minlength=n)
        self.in_degree = torch.from_numpy(indeg.astype(np.int64))
        order = np.argsort(dst, kind="stable")           # edges grouped by dst
        starts = np.concatenate([[0], np.cumsum(indeg)])  # dst-CSR
        widths = np.zeros(n, dtype=np.int64)
        nz = indeg > 0
        widths[nz] = 1 << np.ceil(np.log2(indeg[nz])).astype(np.int64)
        self.buckets = []                                 # (nodes [n_b], edge_of_pad [n_b*w], width)
        edge_of_pad_parts, pad_pos_of_edge = [], np.empty(e, dtype=np.int64)
        offset = 0
        for w in np.unique(widths[nz]):
            nodes = np.flatnonzero(widths == w)
            nb = len(nodes)
            eop = np.full((nb, w), e, dtype=np.int64)     # e == the dummy edge
            # fill row i with the edges of nodes[i] (dst-sorted positions)
            counts = indeg[nodes]
            row = np.repeat(np.arange(nb), counts)
            col = np.arange(counts.sum()) - np.repeat(np.concatenate([[0], np.cumsum(counts)[:-1]]), counts)
            src_pos = np.concatenate([np.arange(starts[j], starts[j + 1]) for j in nodes]) if nb else np.empty(0, np.int64)
            edges = order[src_pos]
            eop[row, col] = edges
            flat = eop.reshape(-1)
            pad_pos_of_edge[edges] = offset + row * w + col
            offset += flat.size
            self.buckets.append((torch.from_numpy(nodes).to(self.device), torch.from_numpy(flat).to(self.device), int(w)))
            edge_of_pad_parts.append(flat)
        self.padded_edges = int(offset)
        edge_of_pad = np.concatenate(edge_of_pad_parts) if edge_of_pad_parts else np.empty(0, np.int64)
        src_ext = np.concatenate([src, [n]])              # dummy edge points at the zero row n
        dst_ext = np.concatenate([dst, [n]])
        self.src_pad = torch.from_numpy(src_ext[edge_of_pad]).to(self.device)     # [padded_edges]
        self.dst_pad = torch.from_numpy(dst_ext[edge_of_pad]).to(self.device)
        self.edge_of_pad = torch.from_numpy(edge_of_pad).to(self.device)
        self.pad_pos_of_edge = torch.from_numpy(pad_pos_of_edge).to(self.device)
        # per-bucket slices into the padded arrays
        self.slices = []
        off = 0
        for nodes, flat, w in self.buckets:
            self.slices.append((off, off + flat.numel()))
            off += flat.numel()


class _SignedAggregate(torch.autograd.Function):
    @staticmethod
    def forward(ctx, h, w, layout: EdgeLayout):
        ctx.save_for_backward(h, w)
        ctx.layout = layout
        return _forward(h, w, layout)

    @staticmethod
    def backward(ctx, grad_out):
        h, w = ctx.saved_tensors
        layout = ctx.layout
        n, B = h.shape
        zero = h.new_zeros(1, B)
        h_pad = torch.cat([h, zero], 0)
        g_pad = torch.cat([grad_out, zero], 0)
        w_pad = torch.cat([w, w.new_zeros(1)], 0)[layout.edge_of_pad]
        grad_h = grad_w = None
        if ctx.needs_input_grad[0]:
            # dL/dh[i] = sum_{e: src_e = i} w_e * grad_out[dst_e]
            gh = h.new_zeros(n + 1, B)
            for (lo, hi) in layout.slices:
                msg = g_pad.index_select(0, layout.dst_pad[lo:hi]) * w_pad[lo:hi, None]
                gh.index_add_(0, layout.src_pad[lo:hi], msg)
            grad_h = gh[:n]
        if ctx.needs_input_grad[1]:
            # dL/dw_e = <h[src_e], grad_out[dst_e]>
            gw_pad = h.new_empty(layout.padded_edges)
            for (lo, hi) in layout.slices:
                a = h_pad.index_select(0, layout.src_pad[lo:hi])
                b = g_pad.index_select(0, layout.dst_pad[lo:hi])
                gw_pad[lo:hi] = (a * b).sum(1)
            grad_w = gw_pad[layout.pad_pos_of_edge]
        return grad_h, grad_w, None


def _forward(h, w, layout: EdgeLayout):
    n, B = h.shape
    h_pad = torch.cat([h, h.new_zeros(1, B)], 0)
    w_pad = torch.cat([w, w.new_zeros(1)], 0)[layout.edge_of_pad]
    out = h.new_zeros(n, B)
    for (nodes, _flat, width), (lo, hi) in zip(layout.buckets, layout.slices):
        msg = h_pad.index_select(0, layout.src_pad[lo:hi]) * w_pad[lo:hi, None]
        out[nodes] = msg.view(len(nodes), width, B).sum(1)
    return out


def signed_aggregate(h: torch.Tensor, w: torch.Tensor, layout: EdgeLayout) -> torch.Tensor:
    """out[dst] += w * h[src], deterministic forward. h: [N, B]; w: [E] (already includes the sign)."""
    if h.shape[0] != layout.n or w.shape[0] != layout.e:
        raise ValueError(f"shape mismatch: h {tuple(h.shape)} w {tuple(w.shape)} layout N={layout.n} E={layout.e}")
    return _SignedAggregate.apply(h, w, layout)
