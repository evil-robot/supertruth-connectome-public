import numpy as np
import pytest

from flytrust.graph import Graph, load_graph, SENSORY_SC, DESCENDING_SC, MOTOR_SC


@pytest.mark.full
def test_full_graph_matches_readme_facts(full_graph):
    g = full_graph
    assert g.n == 166_700
    assert g.e == 6_242_118
    assert g.sensory_mask.sum() == 17_937
    assert g.descending_mask.sum() == 1_316
    assert g.motor_mask.sum() == 815
    assert set(np.unique(g.sign)) <= {-1, 1}
    assert abs((g.sign > 0).mean() - 0.628) < 0.001
    assert g.syn.min() >= 5
    assert g.src.dtype == np.int64 and g.dst.dtype == np.int64
    assert g.meta["n_edges_at_threshold"] == g.e
    assert len(g.meta_sha256) == 64


@pytest.mark.full
def test_csr_expansion_is_consistent(full_graph):
    g = full_graph
    # src is non-decreasing (CSR row expansion) and out-degree from src matches indptr
    assert (np.diff(g.src) >= 0).all()
    outdeg = g.out_degree()
    assert outdeg.sum() == g.e and outdeg.max() == 7570
    indeg = g.in_degree()
    assert indeg.max() == 6660
    assert int(((outdeg == 0) & (indeg == 0)).sum()) == 864


@pytest.mark.full
def test_dales_law_holds_per_presynaptic_neuron(full_graph):
    g = full_graph
    # every outgoing edge of a neuron carries the same sign
    first = np.full(g.n, -127, dtype=np.int8)
    np.maximum.at(first, g.src, g.sign)
    lo = np.full(g.n, 127, dtype=np.int8)
    np.minimum.at(lo, g.src, g.sign)
    has = g.out_degree() > 0
    assert (first[has] == lo[has]).all()


def test_gain_init_is_log1p_synapses(small_graph):
    g = small_graph
    np.testing.assert_allclose(g.gain_init(), np.log1p(g.syn).astype(np.float32))


def test_subgraph_keeps_k_high_degree_neurons_and_induced_edges(full_graph):
    k = 2000
    g = full_graph.subgraph(k, seed=0)
    assert g.n == k
    assert g.e > 0
    assert g.src.max() < k and g.dst.max() < k
    assert g.sensory_mask.sum() > 0
    assert (g.descending_mask | g.motor_mask).sum() > 0
    # induced: every kept edge exists in the full graph between the kept body ids
    full = full_graph
    key_full = set((full.body_id[full.src] * (1 << 40) + full.body_id[full.dst]).tolist())
    key_sub = (g.body_id[g.src] * (1 << 40) + g.body_id[g.dst]).tolist()
    assert all(kk in key_full for kk in key_sub[:5000])
    # sign and synapse count travel with the edge
    lut = {kk: (int(s), int(w)) for kk, s, w in zip(
        (full.body_id[full.src] * (1 << 40) + full.body_id[full.dst]).tolist(), full.sign, full.syn)}
    for kk, s, w in list(zip(key_sub, g.sign, g.syn))[:5000]:
        assert lut[kk] == (int(s), int(w))
    # same k, same seed -> identical; masks are restrictions of the full masks
    g2 = full_graph.subgraph(k, seed=0)
    assert np.array_equal(g.body_id, g2.body_id)
    # the k chosen neurons are high degree: median degree far above full-graph median
    deg = full.in_degree() + full.out_degree()
    pos = np.searchsorted(full.body_id, g.body_id)
    assert np.median(deg[pos]) > 10 * np.median(deg)


def test_role_sets_are_the_readme_sets():
    assert SENSORY_SC == {"ol_sensory", "cb_sensory", "vnc_sensory", "sensory_ascending", "sensory_descending",
                          "cb_sensory_tbc", "vnc_sensory_tbc", "sensory_ascending_tbc"}
    assert DESCENDING_SC == {"descending_neuron", "descending_neuron_tbc"}
    assert MOTOR_SC == {"vnc_motor", "cb_motor"}


def test_graph_from_arrays_validates():
    with pytest.raises(ValueError):
        Graph.from_edges(n=3, src=np.array([0, 5]), dst=np.array([1, 2]), sign=np.array([1, 1], np.int8),
                         syn=np.array([5, 5], np.int32), sensory_mask=np.zeros(3, bool),
                         descending_mask=np.zeros(3, bool), motor_mask=np.zeros(3, bool))
