from .helpers import load_script


def test_seed_data_is_valid_and_broad():
    v = load_script("validate_seed_data")
    systems, per, problems = v.validate()
    assert problems == []
    assert len(systems) >= 50 and len(per) == 12 and min(per.values()) >= 3
    assert any(s.kind == "mechanism" for s in systems)
    assert all(s.sources and s.confidence in ("low", "medium", "high") for s in systems)


def test_seed_data_has_no_em_dashes_and_graphs_are_valid():
    v = load_script("validate_seed_data")
    systems, _, _ = v.validate()
    for s in systems:
        assert s.graph.validate() == []
        assert "\u2014" not in s.summary and "\u2014" not in s.name
