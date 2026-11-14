import random

import pytest

from intelligence.schemas import Graph, Node, ScoreWeights, SchemaError, System, Problem
from intelligence.mapping_engine import map_graphs
from intelligence.analogy_engine import AnalogyEngine
from intelligence.domain_engine import DomainRegistry
from intelligence.structural_model import build_model
from knowledge_base import load_systems, load_domains
from .helpers import load_script

ROLES_POOL = ["source", "sink", "buffer", "conduit", "regulator", "sensor", "controller", "actuator"]
REL_POOL = ["flows_to", "controls", "inhibits", "activates", "signals"]


def rand_graph(seed, n=7, m=10):
    rng = random.Random(seed)
    g = Graph()
    for i in range(n):
        g.add_node(Node(f"n{i}", f"n{i}", role=rng.choice(ROLES_POOL)))
    for _ in range(m):
        g.add_edge(f"n{rng.randrange(n)}", f"n{rng.randrange(n)}", rng.choice(REL_POOL))
    return g


@pytest.mark.parametrize("seed", range(12))
def test_mapping_is_injective_and_reports_every_unmapped_element(seed):
    a, b = rand_graph(seed), rand_graph(seed + 100, n=5, m=6)
    m = map_graphs(a, b)
    src = [s for s, _, _ in m.node_pairs]
    tgt = [t for _, t, _ in m.node_pairs]
    assert len(set(src)) == len(src) and len(set(tgt)) == len(tgt)
    assert set(src) | set(m.unmapped_source) == set(a.node_ids())
    assert set(tgt) | set(m.unmapped_target) == set(b.node_ids())
    # every source edge is accounted for exactly once
    accounted = [p["source_edge"] for p in m.edge_pairs] + [l["source_edge"] for l in m.lost_edges]
    assert sorted(accounted) == sorted(e.id for e in a.edges)
    # roles of mapped pairs are compatible (role constrained)
    ra = {n.id: n.role for n in a.nodes}
    rb = {n.id: n.role for n in b.nodes}
    from intelligence.schemas import ROLE_FAMILIES
    assert all(ra[s] == rb[t] or ROLE_FAMILIES[ra[s]] == ROLE_FAMILIES[rb[t]] for s, t, _ in m.node_pairs)
    assert 0.0 <= m.confidence <= 1.0


def test_identical_graph_maps_fully_and_is_deterministic():
    g = rand_graph(3)
    m1, m2 = map_graphs(g, g), map_graphs(g, g)
    assert m1.to_dict() == m2.to_dict()
    assert m1.edge_f1 > 0.9 and m1.node_coverage == 1.0
    assert not m1.lost_edges and not m1.unmapped_source


def test_no_valid_mapping_when_roles_disjoint():
    a, b = Graph(), Graph()
    a.add_node(Node("x", "x", role="source"))
    b.add_node(Node("y", "y", role="sensor"))
    m = map_graphs(a, b)
    assert m.node_pairs == [] and m.unmapped_source == ["x"] and m.confidence == 0.0


def test_mapping_distinguishes_rewired_graph():
    g = rand_graph(5, n=6, m=7)
    h = Graph.from_dict(g.to_dict())
    tg = [e.target for e in h.edges]
    for e, t in zip(h.edges, tg[1:] + tg[:1]):
        e.target = t
    assert map_graphs(g, g).edge_f1 > map_graphs(g, h).edge_f1


@pytest.fixture(scope="module")
def engine():
    return AnalogyEngine(load_systems(), DomainRegistry(load_domains()))


def test_weights_must_sum_to_100(engine):
    with pytest.raises(SchemaError):
        AnalogyEngine(engine.systems, weights=ScoreWeights(functional=40))


def test_score_is_weighted_sum_of_bounded_components(engine):
    s = engine.by_id["phys_mass_spring_damper"]
    r = engine.search(build_model(s), "physics", top_n=5)
    for m in r.matches:
        assert abs(m.score - sum(c["score"] * c["weight"] for c in m.components.values())) < 1e-3
        assert all(0.0 <= c["score"] <= 1.0 and c["explanation"] for c in m.components.values())
        assert 0.0 <= m.score <= 100.0
    assert r.matches[0].system_id == "phys_mass_spring_damper" and r.matches[0].same_domain
    assert r.matches[1].system_id == "phys_rlc_circuit"


def test_custom_weights_change_score(engine):
    s = engine.by_id["phys_rlc_circuit"]
    e2 = AnalogyEngine(engine.systems, engine.domains, ScoreWeights(25, 25, 20, 15, 10, 5))
    e3 = AnalogyEngine(engine.systems, engine.domains, ScoreWeights(5, 5, 5, 5, 5, 75))
    a = e2.search(build_model(s), "physics", top_n=3).matches[1].score
    b = e3.search(build_model(s), "physics", top_n=3).matches[1].score
    assert a != b


def test_cross_domain_filter_threshold_and_stable_order(engine):
    s = engine.by_id["bio_thermoregulation"]
    q = build_model(s)
    r = engine.search(q, "biology", top_n=10, cross_domain_only=True, threshold=40.0)
    assert all(not m.same_domain and m.domain != "biology" for m in r.matches)
    assert all(m.score >= 40.0 for m in r.matches)
    assert any(x["stage"] == "cross_domain_filter" for x in r.excluded)
    assert r.threshold == 40.0
    order = [(m.score, m.system_id) for m in r.matches]
    assert order == sorted(order, key=lambda t: (-t[0], t[1]))
    assert engine.search(q, "biology", top_n=10).to_dict() == engine.search(q, "biology", top_n=10).to_dict()


def test_domain_distance_reported_not_scored(engine):
    s = engine.by_id["bio_thermoregulation"]
    r = engine.search(build_model(s), "biology", top_n=10)
    m = next(x for x in r.matches if x.domain != "biology")
    assert m.domain_distance > 0 and "domain" not in m.components


def test_empty_knowledge_base_returns_empty_report():
    eng = AnalogyEngine([])
    g = Graph()
    g.add_node(Node("a", "a", role="source"))
    r = eng.search(build_model(Problem("p", "p", "text", graph=g)))
    assert r.matches == [] and r.stage_counts["knowledge_base"] == 0


def test_missing_dynamics_flagged():
    g = Graph()
    for i, role in enumerate(["source", "buffer", "sink"]):
        g.add_node(Node(f"n{i}", f"n{i}", role=role))
    g.add_edge("n0", "n1", "flows_to")
    g.add_edge("n1", "n2", "flows_to")
    s = System("nodyn", "No dynamics", "physics", "x", g, sources=[{"citation": "synthetic"}])
    eng = AnalogyEngine([s])
    q = build_model(Problem("p", "p", "flow", graph=g))
    m = eng.search(q, "physics").matches[0]
    assert m.components["dynamic"]["score"] == 0.0 and "no_dynamics_data" in m.flags


def test_negative_lookalikes_score_below_positives_on_benchmark():
    ev = load_script("evaluate_benchmarks")
    results, summary = ev.run()
    assert summary["pairs"] == 7
    for r in results:
        assert r["positive_score"] > max(r["negative_scores"].values()), r["query"]
    assert summary["positive_beats_all_negatives"] == 7
    assert summary["hit_at_5"] >= 0.85
    # structure matters: lexical-only ranking is clearly worse
    assert summary["mrr_primary"] > summary["mrr_lexical_only_baseline"] + 0.3


def test_declared_feedback_without_a_loop_is_ignored_and_flagged():
    g = Graph()
    for i, role in enumerate(["source", "buffer", "sink"]):
        g.add_node(Node(f"n{i}", f"n{i}", role=role))
    g.add_edge("n0", "n1", "flows_to")
    g.add_edge("n1", "n2", "flows_to")
    s = System("fake", "Fake loop", "physics", "x", g, dynamics=["negative_feedback", "delay"], sources=[{"citation": "synthetic"}])
    m = build_model(s)
    assert "negative_feedback" not in m.dynamics and "delay" in m.dynamics
    assert any("negative_feedback" in f for f in m.flags)
