import math

from intelligence.perception import perceive_text, perceive_csv, perceive_pdf, perceive_image
from intelligence.schemas import Graph, Node, System, ROLES, DYNAMICS_TAGS, CONSTRAINT_TAGS
from intelligence.structural_model import build_model
from intelligence.fingerprint import (compute_fingerprint, semantic_embedding, FINGERPRINT_VERSION, SEMANTIC_DIM,
                                      cosine, build_idf)

ROLLER = ("Strip made of copper or silver must be reduced in thickness. The strip is 50 mm width and 2 mm thickness. "
          "The motor drives the rolls. The rolls reduce the strip. The operator sets the screwdown once per coil. "
          "The screwdown sets the roll gap. The roll gap constrains the rolls. The thickness variation must not exceed 0.02 mm. "
          "The goal is to achieve a 20 % reduction with minimal thickness variation.")


def test_roller_entities_relations_variables_and_constraint():
    r = perceive_text(ROLLER, "roller")
    labels = {n.label: n.role for n in r.problem.graph.nodes}
    assert labels["strip"] == "medium" and labels["motor"] == "actuator" and labels["roll gap"] == "regulator"
    rels = {(e.source, e.relation, e.target) for e in r.problem.graph.edges}
    assert ("motor", "transmits", "roll") in rels and ("roll", "converts", "strip") in rels
    assert ("roll_gap", "constrains", "roll") in rels
    vals = r.problem.values()
    assert vals["width"] == 50.0 and vals["thickness"] == 2.0 and vals["reduction"] == 20.0
    c = r.problem.constraints[0]
    assert c.kind == "hard" and c.expression == {"var": "variation", "op": "<=", "value": 0.02, "unit": "mm"}
    assert "reduction" in r.problem.goal


def test_decimal_numbers_not_split_into_sentences():
    r = perceive_text("The tolerance must not exceed 0.02 mm.", "x")
    assert r.problem.constraints[0].expression["value"] == 0.02


def test_facts_inferences_assumptions_unknowns_are_separated():
    r = perceive_text("The tank and the pump are near each other.", "x")
    assert any("couples" in a["statement"] for a in r.assumptions)  # no verb cue: assumption, not fact
    assert any("inferred as" in i["statement"] for i in r.inferences)
    assert any("no goal" in u for u in r.unknowns)
    assert r.clarification_questions
    assert all(e.provenance.value == "computation" for e in r.problem.graph.edges if "assumed_relation" in e.flags)


def test_empty_and_non_english_input():
    r = perceive_text("   ", "x")
    assert "empty_input" in r.flags and r.unknowns and not r.problem.graph.nodes
    r2 = perceive_text("Das ist ein sehr langer deutscher Satz über Maschinen und Werkzeuge mit vielen Wörtern.", "de")
    assert "low_confidence_non_english" in r2.flags


def test_csv_perception_and_hooks_unavailable():
    csv_text = "speed,force,note\n1,10,a\n2,21,b\n3,29,c\n4,41,d\n5,50,e\n"
    r = perceive_csv(csv_text, "run")
    assert {v.name for v in r.problem.variables} == {"speed", "force"}
    assert any("correlate" in i["statement"] for i in r.inferences)
    assert any("note" in u for u in r.unknowns)
    assert perceive_image("x.png").available is False
    pdf = perceive_pdf("/nonexistent.pdf")
    assert pdf.available is False and "pdf_unavailable" in pdf.flags


def test_determinism_of_perception():
    assert perceive_text(ROLLER, "roller").to_dict() == perceive_text(ROLLER, "roller").to_dict()


def _model(roles_edges):
    g = Graph()
    nodes, edges = roles_edges
    for n, r in nodes:
        g.add_node(Node(n, n, role=r))
    for a, rel, b in edges:
        g.add_edge(a, b, rel)
    s = System("s", "S", "physics", "a simple system", g, behaviours=["regulate"], dynamics=["delay"])
    return build_model(s)


def test_fingerprint_deterministic_versioned_fixed_length():
    m = _model(([("a", "source"), ("b", "buffer"), ("c", "sink")], [("a", "flows_to", "b"), ("b", "flows_to", "c")]))
    f1, f2 = compute_fingerprint(m), compute_fingerprint(m)
    assert f1.hash == f2.hash and f1.to_dict() == f2.to_dict()
    assert f1.schema_version == FINGERPRINT_VERSION
    assert len(f1.dynamic) == len(DYNAMICS_TAGS) and len(f1.constraint) == len(CONSTRAINT_TAGS)
    assert len(f1.semantic) == SEMANTIC_DIM and len(f1.topological) == 12
    assert len(f1.functional) == len(ROLES) + 16


def test_single_node_graph_has_zero_topology():
    m = _model(([("a", "source")], []))
    f = compute_fingerprint(m)
    assert f.topological == [0.0] * 12 and f.hash


def test_fingerprint_changes_when_structure_changes():
    a = _model(([("a", "source"), ("b", "buffer"), ("c", "sink")], [("a", "flows_to", "b"), ("b", "flows_to", "c")]))
    b = _model(([("a", "source"), ("b", "buffer"), ("c", "sink")], [("a", "flows_to", "c"), ("b", "flows_to", "c")]))
    assert compute_fingerprint(a).hash != compute_fingerprint(b).hash


def test_semantic_embedding_is_lexical_unit_norm_and_deterministic():
    e1 = semantic_embedding("water tank level sensor")
    assert e1 == semantic_embedding("water tank level sensor")
    assert abs(math.sqrt(sum(x * x for x in e1)) - 1.0) < 1e-9
    assert cosine(e1, semantic_embedding("tank level of water sensor")) > 0.9
    # synonyms share nothing: this is lexical, not neural
    assert cosine(semantic_embedding("automobile"), semantic_embedding("car")) < 0.5
    idf = build_idf(["alpha beta gamma", "alpha delta omega"])
    assert idf["beta"] > idf["alpha"]
