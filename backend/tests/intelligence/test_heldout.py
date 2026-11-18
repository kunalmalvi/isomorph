"""Phase 6 held-out benchmark: schema, separation from the tuning set, evaluator output and review comparison.

The review file used here is SYNTHETIC. No independent review of the held-out labels has happened.
"""
import json
import os

from knowledge_base import load_systems, load_benchmarks
from .helpers import load_script, ROOT

HELDOUT = os.path.join(ROOT, "data", "benchmark_problems", "heldout_labels.json")
TEMPLATE = os.path.join(ROOT, "data", "benchmark_problems", "review_template.json")


def _doc():
    with open(HELDOUT) as f:
        return json.load(f)


def test_heldout_schema_and_status():
    doc = _doc()
    assert doc["split"] == "heldout"
    assert doc["label_status"] == "author_labelled" and doc["independent_review"] == "none"
    assert len(doc["items"]) >= 20
    for it in doc["items"]:
        q = it["query"]
        assert q["id"] and q["statement"] and q["graph"]["nodes"] and q["graph"]["edges"]
        labels = it["labels"]
        assert any(l["grade"] == 2 for l in labels)
        assert sum(1 for l in labels if l["grade"] < 2) >= 2
        assert any(l["lookalike"] for l in labels)
        for l in labels:
            assert l["grade"] in (0, 1, 2)
            assert l["rationale"].strip()
            assert isinstance(l["role_mapping"], dict)
            assert l["label_status"] == "author_labelled" and l["independent_review"] == "none"
            if l["lookalike"]:
                assert l["grade"] == 0 and l["lookalike_reason"]
            if l["grade"] > 0:
                assert l["role_mapping"]
                node_ids = {n["id"] for n in q["graph"]["nodes"]}
                assert set(l["role_mapping"]) <= node_ids, (q["id"], l["system_id"])


def test_no_overlap_with_tuning_set():
    tuning = {p["query"]["id"] for p in load_benchmarks()["pairs"]}
    assert load_benchmarks()["split"] == "tuning"
    held = {it["query"]["id"] for it in _doc()["items"]}
    assert not (tuning & held)
    tuning_titles = {p["query"]["title"] for p in load_benchmarks()["pairs"]}
    assert not (tuning_titles & {it["query"]["title"] for it in _doc()["items"]})
    assert len(held) == len(_doc()["items"])


def test_every_label_references_existing_system_and_mapping_nodes():
    systems = {s.id: s for s in load_systems()}
    for it in _doc()["items"]:
        for l in it["labels"]:
            assert l["system_id"] in systems, l["system_id"]
            nodes = {n.id for n in systems[l["system_id"]].graph.nodes}
            assert set(l["role_mapping"].values()) <= nodes, (it["query"]["id"], l["system_id"])


def test_review_template_has_one_blank_row_per_label():
    with open(TEMPLATE) as f:
        t = json.load(f)
    n = sum(len(it["labels"]) for it in _doc()["items"])
    assert len(t["rows"]) == n and t["review_status"] == "not_reviewed"
    for r in t["rows"]:
        assert r["reviewer_grade"] is None and r["reviewer_name"] == "" and r["review_date"] == ""


def test_evaluate_heldout_runs_and_emits_banner(capsys):
    ev = load_script("evaluate_heldout")
    rows, summary = ev.run()
    assert summary["queries"] == len(_doc()["items"])
    assert 0.0 <= summary["mrr_strong"] <= 1.0 and 0.0 <= summary["ndcg_at_10"] <= 1.0
    assert "lexical_only" in summary and "lookalike_beats_best_strong" in summary
    assert "NOT INDEPENDENTLY REVIEWED" in ev.BANNER and "AUTHOR-LABELLED" in ev.BANNER


def test_ndcg_math_on_known_example():
    ev = load_script("evaluate_heldout")
    assert abs(ev.ndcg_at(["a", "b"], {"a": 2, "b": 1}) - 1.0) < 1e-9
    # ranking b first then a: dcg = 1 + 3/log2(3), ideal = 3 + 1/log2(3)
    import math
    expected = (1 + 3 / math.log2(3)) / (3 + 1 / math.log2(3))
    assert abs(ev.ndcg_at(["b", "a"], {"a": 2, "b": 1}) - expected) < 1e-9
    assert ev.first_rank(["x", "y", "z"], {"z"}) == 3


def test_compare_reviews_math_on_known_example():
    cr = load_script("compare_reviews")
    # SYNTHETIC review: author [2,2,1,0], reviewer [2,1,1,0]. po = 3/4. pe = .5*.25+.25*.5+.25*.25... computed below.
    rows = [{"item_id": f"s{i}", "author_grade": a, "reviewer_grade": r, "comment": "synthetic"}
            for i, (a, r) in enumerate([(2, 2), (2, 1), (1, 1), (0, 0)])]
    rows.append({"item_id": "skipped", "author_grade": 2, "reviewer_grade": None})
    res = cr.compare({"rows": rows})
    assert res["rows_reviewed"] == 4 and res["rows_total"] == 5
    assert res["percent_agreement"] == 75.0
    pe = (2 / 4) * (1 / 4) + (1 / 4) * (2 / 4) + (1 / 4) * (1 / 4)
    assert abs(res["cohens_kappa"] - round((0.75 - pe) / (1 - pe), 4)) < 1e-9
    assert [d["item_id"] for d in res["disputed"]] == ["s1"]
    # perfect agreement gives kappa 1
    same = [{"item_id": "a", "author_grade": 2, "reviewer_grade": 2}, {"item_id": "b", "author_grade": 0, "reviewer_grade": 0}]
    assert cr.compare({"rows": same})["cohens_kappa"] == 1.0
