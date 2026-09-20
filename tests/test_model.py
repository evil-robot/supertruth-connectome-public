import numpy as np
import pytest
import torch

from flytrust.model import ConnectomeNet, OutputSpec, DTI_SPEC, BII_SPEC, count_parameters


def test_output_specs():
    assert DTI_SPEC.total_dim == 8 + 1 + 5
    assert BII_SPEC.total_dim == 1 + 4
    assert [h.name for h in DTI_SPEC.heads] == ["dims", "composite", "tier"]
    assert DTI_SPEC.classes["tier"] == ["BELOW THRESHOLD", "BRONZE", "SILVER", "GOLD", "PLATINUM"]
    assert BII_SPEC.classes["gate"] == ["COLLAPSE", "ALERT", "HOLD", "PASS"]


def test_forward_shapes_and_heads(small_graph, devices):
    F = 16
    for dev in devices:
        net = ConnectomeNet(small_graph, in_dim=F, spec=DTI_SPEC, T=4, device=dev)
        x = torch.randn(5, F, device=dev)
        out = net(x)
        assert set(out) == {"dims", "composite", "tier"}
        assert out["dims"].shape == (5, 8) and out["composite"].shape == (5, 1) and out["tier"].shape == (5, 5)
        assert torch.isfinite(out["dims"]).all()


def test_parameter_count_formula(small_graph):
    F = 16
    net = ConnectomeNet(small_graph, in_dim=F, spec=DTI_SPEC, T=4, device="cpu")
    g = small_graph
    n_sens = int(g.sensory_mask.sum()); n_ro = int(g.readout_mask.sum())
    expected = (g.e            # theta_e (per-edge gain magnitude)
                + 1            # global gain scale
                + 3 * g.n      # bias, leak logit, homeostatic gain
                + F * n_sens + n_sens          # W_in
                + n_ro * DTI_SPEC.total_dim + DTI_SPEC.total_dim)  # readout
    assert count_parameters(net) == expected
    assert net.parameter_breakdown()["theta"] == g.e


def test_gain_initialised_to_log1p_synapses_and_sign_fixed(small_graph):
    net = ConnectomeNet(small_graph, in_dim=4, spec=BII_SPEC, T=2, device="cpu")
    g = net.edge_gain().detach().cpu().numpy()
    np.testing.assert_allclose(g, np.log1p(small_graph.syn), rtol=1e-5, atol=1e-5)
    assert not net.sign.requires_grad
    assert torch.equal(net.sign.cpu(), torch.from_numpy(small_graph.sign.astype(np.float32)))
    assert torch.allclose(net.leak().detach(), torch.full((small_graph.n,), 0.5))
    assert torch.allclose(net.homeo_gain.detach(), torch.ones(small_graph.n))


def test_forward_is_deterministic_and_batch_consistent(small_graph, devices):
    for dev in devices:
        net = ConnectomeNet(small_graph, in_dim=8, spec=BII_SPEC, T=6, device=dev).eval()
        x = torch.randn(7, 8, device=dev)
        with torch.no_grad():
            a, b = net(x), net(x)
        for k in a:
            assert torch.equal(a[k], b[k]), f"{k} nondeterministic on {dev}"
        # record 3 alone vs inside the batch: same up to float reordering in matmul
        with torch.no_grad():
            single = net(x[3:4])
        torch.testing.assert_close(single["bii"], a["bii"][3:4], rtol=1e-4, atol=1e-4)


def test_activity_bounded_over_time(small_graph):
    # total_gain normalisation: at init each pre-activation is a signed weighted average of its inputs, so the
    # hidden state stays bounded by the sensory drive for any T.
    net = ConnectomeNet(small_graph, in_dim=8, spec=BII_SPEC, T=8, device="cpu")
    x = torch.randn(3, 8)
    hs = net.hidden_trajectory(x)
    norms = [h.norm().item() for h in hs]
    assert all(np.isfinite(norms))
    assert norms[-1] < 10 * (norms[1] + 1e-6)
    # converging: the last step moves the state far less than the second one did
    assert (hs[-1] - hs[-2]).norm() < 0.5 * (hs[2] - hs[1]).norm()
    assert hs[-1].abs().sum() > 0                            # and activity does propagate
    # the sqrt_degree alternative explodes on this high-degree subgraph (documented in model.py)
    alt = ConnectomeNet(small_graph, in_dim=8, spec=BII_SPEC, T=8, device="cpu", norm="sqrt_degree")
    n2 = [h.norm().item() for h in alt.hidden_trajectory(x)]
    assert n2[-1] > 1000 * n2[1]


def test_gradients_reach_every_parameter_group(small_graph):
    net = ConnectomeNet(small_graph, in_dim=8, spec=DTI_SPEC, T=3, device="cpu")
    x = torch.randn(4, 8)
    out = net(x)
    loss = sum(o.pow(2).mean() for o in out.values())
    loss.backward()
    for name, p in net.named_parameters():
        assert p.grad is not None and torch.isfinite(p.grad).all(), name
    assert net.theta.grad.abs().sum() > 0
    assert net.w_in.weight.grad.abs().sum() > 0


def test_custom_output_spec(small_graph):
    spec = OutputSpec.build([("score", "regression", 3), ("cls", "classification", ["a", "b"])])
    net = ConnectomeNet(small_graph, in_dim=4, spec=spec, T=2, device="cpu")
    out = net(torch.randn(2, 4))
    assert out["score"].shape == (2, 3) and out["cls"].shape == (2, 2)
