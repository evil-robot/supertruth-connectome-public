import pytest
import torch

from flytrust.graph import load_graph


@pytest.fixture(scope="session")
def full_graph():
    return load_graph()


@pytest.fixture(scope="session")
def small_graph(full_graph):
    return full_graph.subgraph(2000, seed=0)


@pytest.fixture(scope="session")
def devices():
    out = [torch.device("cpu")]
    if torch.backends.mps.is_available():
        out.append(torch.device("mps"))
    return out
