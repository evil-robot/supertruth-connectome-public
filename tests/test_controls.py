import numpy as np
import pytest
import torch

from flytrust.controls import (degree_preserving_shuffle, erdos_renyi, MatchedMLP, RidgeReadout,
                               solve_hidden_width, build_arm)
from flytrust.model import ConnectomeNet, DTI_SPEC, BII_SPEC, count_parameters


def _dale_ok(g):
    hi = np.full(g.n, -127, np.int8); lo = np.full(g.n, 127, np.int8)
    np.maximum.at(hi, g.src, g.sign); np.minimum.at(lo, g.src, g.sign)
    has = g.out_degree() > 0
    return (hi[has] == lo[has]).all()


def test_shuffle_preserves_degrees_edges_signs(small_graph):
    g = small_graph
    s = degree_preserving_shuffle(g, seed=1, swaps_per_edge=1.0)
    assert s.n == g.n and s.e == g.e
    assert np.array_equal(s.in_degree(), g.in_degree())
    assert np.array_equal(s.out_degree(), g.out_degree())
    # per-edge sign stays attached to the presynaptic neuron, so Dale's law still holds
    src_sign = np.zeros(g.n, np.int8); src_sign[g.src] = g.sign
    assert np.array_equal(s.sign, src_sign[s.src])
    assert _dale_ok(s)
    # synapse counts travel with their edge (same multiset per presynaptic neuron)
    for i in np.random.default_rng(0).choice(g.n, 20):
        assert sorted(g.syn[g.src == i]) == sorted(s.syn[s.src == i])
    # no duplicates, no new self-loops, and the wiring actually changed
    keys = s.src * g.n + s.dst
    assert len(np.unique(keys)) == g.e
    assert ((s.src == s.dst).sum()) <= ((g.src == g.dst).sum())
    same = len(np.intersect1d(keys, g.src * g.n + g.dst))
    assert same < 0.5 * g.e
    # role masks and seeding
    assert np.array_equal(s.sensory_mask, g.sensory_mask)
    s2 = degree_preserving_shuffle(g, seed=1, swaps_per_edge=1.0)
    assert np.array_equal(s2.src, s.src) and np.array_equal(s2.dst, s.dst)
    s3 = degree_preserving_shuffle(g, seed=2, swaps_per_edge=1.0)
    assert not np.array_equal(s3.dst, s.dst)


def test_er_has_same_n_e_and_excitatory_fraction(small_graph):
    g = small_graph
    r = erdos_renyi(g, seed=3, exc_fraction=0.628)
    assert r.n == g.n and r.e == g.e
    assert abs(r.excitatory_fraction - 0.628) < 0.005
    assert _dale_ok(r)
    keys = r.src * g.n + r.dst
    assert len(np.unique(keys)) == g.e and not (r.src == r.dst).any()
    assert sorted(r.syn.tolist()) == sorted(g.syn.tolist())      # same synapse-count multiset
    # degree sequence is NOT preserved (that is the point of ER)
    assert not np.array_equal(r.in_degree(), g.in_degree())
    assert np.array_equal(r.motor_mask, g.motor_mask)


def test_solve_hidden_width():
    for target in (10_000, 500_000, 8_000_000):
        H = solve_hidden_width(in_dim=64, out_dim=14, target=target, depth=2)
        params = 64 * H + H + H * H + H + H * 14 + 14
        assert abs(params - target) / target < 0.02


def test_matched_mlp_param_count_within_2pct(small_graph):
    net = ConnectomeNet(small_graph, in_dim=32, spec=DTI_SPEC, T=2, device="cpu")
    target = count_parameters(net)
    mlp = MatchedMLP(in_dim=32, spec=DTI_SPEC, target_params=target)
    got = count_parameters(mlp)
    assert abs(got - target) / target <= 0.02, (got, target)
    out = mlp(torch.randn(3, 32))
    assert out["dims"].shape == (3, 8) and out["tier"].shape == (3, 5)


def test_ridge_readout_recovers_linear_map():
    torch.manual_seed(0)
    X = torch.randn(500, 10)
    W = torch.randn(10, 1)
    y = X @ W
    cls = (y[:, 0] > 0).long()
    r = RidgeReadout(in_dim=10, spec=BII_SPEC, lam=1e-6)
    r.fit(X, {"bii": y, "gate": cls % 4})
    out = r(X)
    torch.testing.assert_close(out["bii"], y, rtol=1e-3, atol=1e-3)
    assert out["gate"].shape == (500, 4)
    assert count_parameters(r) == 0    # closed form, nothing trained by gradient


def test_build_arm_dispatch(small_graph):
    for arm in ("connectome", "shuffle", "er", "mlp", "ridge"):
        m, meta = build_arm(arm, small_graph, in_dim=8, spec=BII_SPEC, T=2, device="cpu", seed=0)
        assert meta["arm"] == arm
        if arm != "ridge":
            out = m(torch.randn(2, 8))
            assert out["bii"].shape == (2, 1)
