"""Phase 6 knowledge base growth: provenance metadata, source confidence and validator behaviour."""
import copy

from knowledge_base import load_systems
from .helpers import load_script


def _v():
    return load_script("validate_seed_data")


def test_kb_size_and_unique_ids():
    systems = load_systems()
    ids = [s.id for s in systems]
    assert len(ids) == len(set(ids))
    assert len(systems) >= 100
    assert sum(1 for s in systems if s.kind == "mechanism") >= 24
    assert all(s.sources for s in systems)


def test_every_system_and_source_has_metadata():
    for s in load_systems():
        assert s.provenance_class in ("sourced", "hypothesis"), s.id
        for src in s.sources:
            assert src["confidence"] in ("high", "medium", "low"), s.id
            assert src["verification"] == "unverified_no_network", s.id
            assert src["claim_scope"], s.id


def test_no_sourced_system_without_source_and_metadata_round_trips():
    for s in load_systems():
        if s.provenance_class == "sourced":
            assert len(s.sources) >= 1
        d = s.to_dict()
        assert d["provenance_class"] == s.provenance_class
        assert d["sources"] == s.sources


def test_new_phase6_systems_present_in_every_domain():
    systems = load_systems()
    c_ids = {"bio_calcium_homeostasis", "phys_rc_charging", "math_sir_epidemic", "log_conwip", "trans_littles_law"}
    assert c_ids <= {s.id for s in systems}
    assert any(s.provenance_class == "hypothesis" for s in systems)


def test_validator_passes_on_real_kb():
    _, per, problems = _v().validate()
    assert problems == []
    assert len(per) == 12 and min(per.values()) >= 6


def test_validator_rejects_bad_entries():
    v = _v()
    base = next(s for s in load_systems() if s.sources)

    def probs(mutate):
        s = copy.deepcopy(base)
        mutate(s)
        return v.check_system_metadata(s, {})

    assert any("no sources" in p for p in probs(lambda s: setattr(s, "sources", [])))
    assert any("provenance_class" in p for p in probs(lambda s: setattr(s, "provenance_class", "made_up")))
    assert any("verified" in p or "verification" in p for p in probs(lambda s: s.sources[0].update(verification="verified")))
    assert any("confidence" in p for p in probs(lambda s: s.sources[0].pop("confidence")))
    assert any("suspicious" in p for p in probs(lambda s: s.sources[0].update(citation="See https://example.org/paper for details")))


def test_validator_rejects_conflicting_duplicate_citation():
    v = _v()
    a, b = [copy.deepcopy(s) for s in load_systems()[:2]]
    cite = a.sources[0]["citation"]
    b.sources = [dict(a.sources[0])]
    b.sources[0]["confidence"] = "low" if a.sources[0]["confidence"] != "low" else "high"
    seen = {}
    assert v.check_system_metadata(a, seen) == []
    assert any("conflicts" in p for p in v.check_system_metadata(b, seen))
    assert cite
