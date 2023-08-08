from __future__ import annotations

from functools import partial

import numpy as np
import pytest
import torch

from matgl.ext.pymatgen import Structure2Graph, get_element_list
from matgl.graph.compute import (
    compute_pair_vector_and_distance,
    compute_theta,
    compute_theta_and_phi,
    create_directed_line_graph,
    create_line_graph,
    prune_edges_by_features,
)


def _loop_indices(bond_atom_indices, pair_dist, cutoff=4.0):
    bin_count = np.bincount(bond_atom_indices[:, 0], minlength=bond_atom_indices[-1, 0] + 1)
    indices = []
    start = 0
    for bcont in bin_count:
        for i in range(bcont):
            for j in range(bcont):
                if start + i == start + j:
                    continue
                if pair_dist[start + i] > cutoff or pair_dist[start + j] > cutoff:
                    continue
                indices.append([start + i, start + j])
        start += bcont
    return np.array(indices)


def _calculate_cos_loop(graph, threebody_cutoff=4.0):
    """
    Calculate the cosine theta of triplets using loops
    Args:
        graph: List
    Returns: a list of cosine theta values.
    """
    _, _, n_sites = torch.unique(graph.edges()[0], return_inverse=True, return_counts=True)
    start_index = 0
    cos = []
    for n_site in n_sites:
        for i in range(n_site):
            for j in range(n_site):
                if i == j:
                    continue
                vi = graph.edata["bond_vec"][i + start_index].numpy()
                vj = graph.edata["bond_vec"][j + start_index].numpy()
                di = np.linalg.norm(vi)
                dj = np.linalg.norm(vj)
                if (di <= threebody_cutoff) and (dj <= threebody_cutoff):
                    cos.append(vi.dot(vj) / np.linalg.norm(vi) / np.linalg.norm(vj))
        start_index += n_site
    return cos


class TestCompute:
    def test_compute_pair_vector(self, graph_Mo):
        s1, g1, state1 = graph_Mo
        bv, bd = compute_pair_vector_and_distance(g1)
        g1.edata["bond_vec"] = bv
        d = torch.linalg.norm(g1.edata["bond_vec"], axis=1)

        _, _, _, d2 = s1.get_neighbor_list(r=5.0)

        np.testing.assert_array_almost_equal(np.sort(d), np.sort(d2))

    def test_compute_pair_vector_for_molecule(self, graph_CH4):
        s2, g2, state2 = graph_CH4
        bv, bd = compute_pair_vector_and_distance(g2)
        g2.edata["bond_vec"] = bv
        d = torch.linalg.norm(g2.edata["bond_vec"], axis=1)

        d2 = np.array(
            [
                1.089,
                1.089,
                1.089,
                1.089,
                1.089,
                1.089,
                1.089,
                1.089,
                1.77833,
                1.77833,
                1.77833,
                1.77833,
                1.77833,
                1.77833,
                1.77833,
                1.77833,
                1.77833,
                1.77833,
                1.77833,
                1.77833,
            ]
        )

        np.testing.assert_array_almost_equal(np.sort(d), np.sort(d2))

    def test_compute_angle(self, graph_Mo, graph_CH4):
        s1, g1, state1 = graph_Mo
        bv, bd = compute_pair_vector_and_distance(g1)
        g1.edata["bond_vec"] = bv
        g1.edata["bond_dist"] = bd
        cos_loop = _calculate_cos_loop(g1, 4.0)

        line_graph = create_line_graph(g1, 4.0)
        line_graph.apply_edges(compute_theta_and_phi)
        np.testing.assert_array_almost_equal(
            np.sort(np.array(cos_loop)), np.sort(np.array(line_graph.edata["cos_theta"]))
        )

        # test only compute theta
        line_graph.apply_edges(partial(compute_theta, directed=False))
        np.testing.assert_array_almost_equal(
            np.sort(np.arccos(np.array(cos_loop) * (1 - 1e-7))), np.sort(np.array(line_graph.edata["theta"]))
        )

        # test only compute theta with cosine
        _ = line_graph.edata.pop("cos_theta")
        line_graph.apply_edges(partial(compute_theta, cosine=True, directed=False))
        np.testing.assert_array_almost_equal(
            np.sort(np.array(cos_loop)), np.sort(np.array(line_graph.edata["cos_theta"]))
        )

        s2, g2, state2 = graph_CH4

        bv, bd = compute_pair_vector_and_distance(g2)
        g2.edata["bond_vec"] = bv
        g2.edata["bond_dist"] = bd
        cos_loop = _calculate_cos_loop(g2, 2.0)

        line_graph = create_line_graph(g2, 2.0)
        line_graph.apply_edges(compute_theta_and_phi)
        np.testing.assert_array_almost_equal(
            np.sort(np.array(cos_loop)), np.sort(np.array(line_graph.edata["cos_theta"]))
        )

        # test only compute theta
        line_graph.apply_edges(partial(compute_theta, directed=False))
        np.testing.assert_array_almost_equal(
            np.sort(np.arccos(np.array(cos_loop))), np.sort(np.array(line_graph.edata["theta"]))
        )

        # test only compute theta with cosine
        _ = line_graph.edata.pop("cos_theta")
        line_graph.apply_edges(partial(compute_theta, cosine=True, directed=False))
        np.testing.assert_array_almost_equal(
            np.sort(np.array(cos_loop)), np.sort(np.array(line_graph.edata["cos_theta"]))
        )


@pytest.mark.parametrize("keep_ndata", [True, False])
@pytest.mark.parametrize("keep_edata", [True, False])
def test_remove_edges_by_features(graph_Mo, keep_ndata, keep_edata):
    s1, g1, state1 = graph_Mo
    bv, bd = compute_pair_vector_and_distance(g1)
    g1.edata["bond_vec"] = bv
    g1.edata["bond_dist"] = bd

    new_cutoff = 3.0
    converter = Structure2Graph(element_types=get_element_list([s1]), cutoff=new_cutoff)
    g2, state2 = converter.get_graph(s1)

    # remove edges by features
    new_g = prune_edges_by_features(
        g1, "bond_dist", condition=lambda x: x > new_cutoff, keep_ndata=keep_ndata, keep_edata=keep_edata
    )
    valid_edges = g1.edata["bond_dist"] <= new_cutoff

    assert new_g.num_edges() == g2.num_edges()
    assert new_g.num_nodes() == g2.num_nodes()
    assert torch.allclose(new_g.edata["edge_ids"], valid_edges.nonzero().squeeze())

    if keep_ndata:
        assert new_g.ndata.keys() == g1.ndata.keys()

    if keep_edata:
        for key in g1.edata:
            if key != "edge_ids":
                assert torch.allclose(new_g.edata[key], g1.edata[key][valid_edges])


def test_directed_line_graph(graph_Mo, graph_CH4):
    s1, g1, state1 = graph_Mo
    bv, bd = compute_pair_vector_and_distance(g1)
    print(max(bd))
    g1.edata["bond_vec"] = bv
    g1.edata["bond_dist"] = bd
    cos_loop = _calculate_cos_loop(g1, 4.0)
    theta_loop = np.arccos(np.array(cos_loop) * (1 - 1e-7))

    line_graph = create_directed_line_graph(g1, 4.0)

    line_graph.apply_edges(compute_theta)
    # need to shift by pi since bond vectors are directed
    line_graph.edata["theta"] = torch.pi - line_graph.edata["theta"]
    np.testing.assert_array_almost_equal(np.sort(theta_loop), np.sort(np.array(line_graph.edata["theta"])))

    s2, g2, state2 = graph_CH4
    bv, bd = compute_pair_vector_and_distance(g2)
    g2.edata["bond_vec"] = bv
    g2.edata["bond_dist"] = bd
    cos_loop = _calculate_cos_loop(g2, 2.0)
    theta_loop = np.arccos(np.array(cos_loop))

    line_graph = create_directed_line_graph(g2, 2.0)
    line_graph.apply_edges(compute_theta)
    # need to shift by pi since bond vectors are directed
    line_graph.edata["theta"] = torch.pi - line_graph.edata["theta"]
    np.testing.assert_array_almost_equal(np.sort(theta_loop), np.sort(np.array(line_graph.edata["theta"])))
