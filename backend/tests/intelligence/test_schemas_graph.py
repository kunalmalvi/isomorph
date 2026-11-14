import pytest

from intelligence.schemas import (Graph, Node, Edge, Problem, Constraint, Variable, System, ScoreWeights, Provenance,
                                  SchemaError, UNCLASSIFIED)
from intelligence.graph_engine import (degrees, strongly_connected_components, find_cycles, feedback_loops, depth,
                                       max_flow, betweenness_centrality, closeness_centrality, pagerank, motifs, metrics,
                                       weakly_connected_components)


def g_from(nodes, edges):
    g = Graph()
    for n in nodes:
        g.add_node(Node(n, n, role="conduit"))
    for a, rel, b, *w in edges:
        g.add_edge(a, b, rel, w[0] if w else 1.0)
    return g


def test_roundtrip_and_provenance_enum():
    g = g_from("abc", [("a", "flows_to", "b"), ("b", "inhibits", "c")])
    p = Problem("p", "t", "s", "g", g, [Constraint("c1", "d", "hard", {"var": "x", "op": "<=", "value": 1})],
                [Variable("x", "mm", 0, 1, "parameter", 0.5)])
    p2 = Problem.from_dict(p.to_dict())
    assert p2.to_dict() == p.to_dict()
    assert p2.graph.nodes[0].provenance is Provenance.SOURCE
    with pytest.raises(SchemaError):
        Node.from_dict({"id": "x", "provenance": "magic"})


def test_unknown_relation_is_kept_as_unclassified_and_flagged():
    g = g_from("ab", [])
    e = g.add_edge("a", "b", "befriends")
    assert e.relation == UNCLASSIFIED and any("unclassified_relation:befriends" in f for f in e.flags)
    assert g.validate() == []


def test_validate_detects_problems():
    g = g_from("ab", [("a", "flows_to", "b")])
    g.edges.append(Edge("e9", "a", "zzz", "flows_to"))
    assert any("unknown node" in p for p in g.validate())
    with pytest.raises(SchemaError):
        g.add_node(Node("a", "dup"))


def test_weights_validation():
    ScoreWeights().validate()
    with pytest.raises(SchemaError):
        ScoreWeights(functional=30).validate()
    with pytest.raises(SchemaError):
        ScoreWeights(functional=-5, relationship=55).validate()


def test_system_validation_requires_sources_and_roles():
    g = g_from("abc", [("a", "flows_to", "b")])
    s = System("s", "S", "physics", "sum", g)
    probs = s.validate()
    assert any("no sources" in p for p in probs)
    g.nodes[0].role = None
    assert any("without functional role" in p for p in s.validate())


# ---- graph metrics on known graphs
def test_degrees_scc_cycles_depth():
    g = g_from("abcde", [("a", "flows_to", "b"), ("b", "flows_to", "c"), ("c", "flows_to", "a"), ("c", "flows_to", "d"), ("d", "flows_to", "e")])
    d = degrees(g)
    assert d["c"] == {"in": 1, "out": 2, "total": 3}
    assert strongly_connected_components(g) == [["a", "b", "c"], ["d"], ["e"]]
    assert find_cycles(g) == [["a", "b", "c"]]
    assert depth(g) == 2
    assert len(weakly_connected_components(g)) == 1


def test_feedback_loop_polarity():
    g = g_from("abc", [("a", "activates", "b"), ("b", "inhibits", "c"), ("c", "activates", "a")])
    loops = feedback_loops(g)
    assert len(loops) == 1 and loops[0]["polarity"] == "negative"
    g2 = g_from("ab", [("a", "activates", "b"), ("b", "activates", "a")])
    assert feedback_loops(g2)[0]["polarity"] == "positive"


def test_self_loop_and_parallel_edges():
    g = g_from("ab", [("a", "activates", "a"), ("a", "flows_to", "b"), ("a", "flows_to", "b")])
    assert find_cycles(g) == [["a"]]
    assert degrees(g)["a"]["out"] == 3
    assert motifs(g)["self_loop"] == 1


def test_max_flow_clrs_example():
    # Cormen et al. flow network, max flow 23
    edges = [("s", "v1", 16), ("s", "v2", 13), ("v1", "v3", 12), ("v2", "v1", 4), ("v2", "v4", 14), ("v3", "v2", 9),
             ("v3", "t", 20), ("v4", "v3", 7), ("v4", "t", 4)]
    g = g_from(["s", "v1", "v2", "v3", "v4", "t"], [(a, "flows_to", b, w) for a, b, w in edges])
    val, flow = max_flow(g, "s", "t")
    assert val == 23
    # capacity respected
    cap = {f"e{i + 1}": w for i, (_, _, w) in enumerate(edges)}
    assert all(flow[k] <= cap[k] + 1e-9 for k in flow)


def test_centrality_on_path_and_pagerank():
    g = g_from("abc", [("a", "flows_to", "b"), ("b", "flows_to", "c")])
    bc = betweenness_centrality(g, normalized=False)
    assert bc["b"] == 1.0 and bc["a"] == 0.0
    assert closeness_centrality(g)["a"] > closeness_centrality(g)["c"]
    pr = pagerank(g)
    assert abs(sum(pr.values()) - 1.0) < 1e-9 and pr["c"] > pr["a"]


def test_motifs_feed_forward_and_empty_graph():
    g = g_from("abc", [("a", "flows_to", "b"), ("b", "flows_to", "c"), ("a", "flows_to", "c")])
    assert motifs(g)["feed_forward_loop"] == 1
    m = metrics(Graph())
    assert m["node_count"] == 0 and m["density"] == 0.0 and m["depth"] == 0


def test_disconnected_graph_metrics():
    g = g_from("abcd", [("a", "flows_to", "b"), ("c", "flows_to", "d")])
    assert metrics(g)["components"] == 2
