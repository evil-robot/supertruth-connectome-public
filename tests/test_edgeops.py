import numpy as np
import pytest
import torch

from flytrust.edgeops import EdgeLayout, signed_aggregate


def _random_graph(n, e, seed):
    rng = np.random.default_rng(seed)
    src = rng.integers(0, n, e).astype(np.int64)
    dst = rng.integers(0, n, e).astype(np.int64)
    # a few very high in-degree targets to exercise wide buckets
    dst[: e // 4] = rng.integers(0, 3, e // 4)
    return src, dst


def _dense_reference(n, src, dst, w, h):
    A = torch.zeros(n, n, dtype=h.dtype)
    A.index_put_((torch.as_tensor(dst), torch.as_tensor(src)), w, accumulate=True)
    return A @ h


@pytest.mark.parametrize("n,e", [(50, 400), (300, 5000)])
def test_matches_dense_reference_on_cpu(n, e):
    src, dst = _random_graph(n, e, 1)
    layout = EdgeLayout(n, src, dst, torch.device("cpu"))
    assert layout.padded_edges >= e and layout.padded_edges <= 2 * e + n
    w = torch.randn(e, dtype=torch.float64)
    h = torch.randn(n, 7, dtype=torch.float64)
    out = signed_aggregate(h, w, layout)
    ref = _dense_reference(n, src, dst, w, h)
    torch.testing.assert_close(out, ref)


def test_gradcheck_wrt_h_and_w():
    n, e = 40, 300
    src, dst = _random_graph(n, e, 2)
    layout = EdgeLayout(n, src, dst, torch.device("cpu"))
    w = torch.randn(e, dtype=torch.float64, requires_grad=True)
    h = torch.randn(n, 3, dtype=torch.float64, requires_grad=True)
    assert torch.autograd.gradcheck(lambda hh, ww: signed_aggregate(hh, ww, layout), (h, w))


def test_zero_in_degree_rows_are_zero():
    n = 20
    src = np.array([0, 1, 2], np.int64)
    dst = np.array([5, 5, 6], np.int64)
    layout = EdgeLayout(n, src, dst, torch.device("cpu"))
    h = torch.ones(n, 2)
    w = torch.tensor([1.0, 2.0, -1.0])
    out = signed_aggregate(h, w, layout)
    assert out[5].tolist() == [3.0, 3.0] and out[6].tolist() == [-1.0, -1.0]
    mask = torch.ones(n, dtype=torch.bool)
    mask[[5, 6]] = False
    assert out[mask].abs().sum() == 0


def test_in_degree_from_layout():
    n = 6
    src = np.array([0, 1, 2, 3], np.int64)
    dst = np.array([5, 5, 5, 0], np.int64)
    layout = EdgeLayout(n, src, dst, torch.device("cpu"))
    assert layout.in_degree.tolist() == [1, 0, 0, 0, 0, 3]


@pytest.mark.full
def test_full_graph_forward_is_bitwise_deterministic(full_graph, devices):
    g = full_graph
    for dev in devices:
        layout = EdgeLayout(g.n, g.src, g.dst, dev)
        assert layout.padded_edges <= 2 * g.e
        gen = torch.Generator().manual_seed(0)
        w = (torch.randn(g.e, generator=gen) * torch.from_numpy(g.sign.astype(np.float32))).to(dev)
        h = torch.randn(g.n, 8, generator=gen).to(dev)
        a = signed_aggregate(h, w, layout)
        b = signed_aggregate(h, w, layout)
        assert torch.equal(a, b), f"nondeterministic on {dev}"
        # and agrees with a plain index_add_ (up to float reordering)
        msg = h.index_select(0, torch.from_numpy(g.src).to(dev)) * w[:, None]
        ref = torch.zeros(g.n, 8, device=dev).index_add_(0, torch.from_numpy(g.dst).to(dev), msg)
        torch.testing.assert_close(a, ref, rtol=1e-4, atol=1e-3)
