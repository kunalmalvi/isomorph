"""Stdlib tests for phase 3 follow-ups: annotation cleanup, all-source seed links, upload interpretation flag."""
import json
import shutil

import pytest

from core.errors import ValidationFailed
from core.uploads import interpretation, store_upload, validate_upload
from database.seed import DEFAULT_DATA_DIR, MemorySink, apply_plan, plan_seed
from intelligence.perception import perceive_text
from services.annotations import InMemoryAnnotationStore, JsonFileAnnotationStore


# ------------------------------------------------------------------ annotation cleanup
@pytest.mark.parametrize("make", [lambda tmp: InMemoryAnnotationStore(), lambda tmp: JsonFileAnnotationStore(str(tmp))])
def test_purge_and_orphan_cleanup(make, tmp_path):
    st = make(tmp_path)
    for run in ("r1", "r2", "r3"):
        st.set(run, "H1", "saved", "n")
    assert st.purge_run("r1") and not st.purge_run("r1") and st.list("r1") == {}
    assert st.cleanup_orphans(["r2"]) == ["r3"]
    assert st.list("r2")["H1"]["note"] == "n" and st.list("r3") == {}
    assert st.cleanup_orphans(["r2"]) == []


def test_cleanup_removes_files_and_ignores_foreign_files(tmp_path):
    st = JsonFileAnnotationStore(str(tmp_path))
    st.set("gone", "H1", "saved", "")
    (tmp_path / "keep.txt").write_text("x")
    assert st.cleanup_orphans([]) == ["gone"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["keep.txt"]


# ------------------------------------------------------------------ seed links every source
def _data_with_sources(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(DEFAULT_DATA_DIR, data)
    for folder in ("seed_knowledge", "mechanisms"):
        for fp in sorted((data / folder).glob("*.json")):
            doc = json.loads(fp.read_text())
            doc["systems"][0]["sources"] = [{"citation": f"First {folder}", "kind": "paper"},
                                            {"citation": f"Second {folder}", "kind": "book"},
                                            {"citation": f"First {folder}", "kind": "paper"}]
            fp.write_text(json.dumps(doc))
            break
    return str(data)


def test_every_citation_is_linked_for_systems_and_mechanisms(tmp_path):
    plan = plan_seed(_data_with_sources(tmp_path))
    multi = [s for s in plan["systems"] if len(s["sources"]) > 1]
    assert len(multi) >= 2 and all(s["sources"][0] == s["source"] for s in multi)
    sink = MemorySink()
    created = apply_plan(plan, sink)
    links = sink.rows["domain_system_sources"]
    assert len(links) == sum(len(s["sources"]) for s in plan["systems"]) and created["domain_system_sources"] == len(links)
    mech_links = sink.rows["mechanism_sources"]
    assert len(mech_links) == sum(len(m["sources"]) for m in plan["mechanisms"])
    assert any(len(m["sources"]) == 2 for m in plan["mechanisms"])
    again = apply_plan(plan, sink)
    assert all(v == 0 for v in again.values())


# ------------------------------------------------------------------ uploads
def test_interpretation_flag():
    assert interpretation("text") == {"interpreted": True, "note": None}
    for kind in ("pdf", "png", "jpeg", "json"):
        r = interpretation(kind)
        assert r["interpreted"] is False and "NOT read" in r["note"]


def test_pdf_is_stored_and_flagged_not_interpreted(tmp_path):
    up = validate_upload("paper.pdf", b"%PDF-1.4 fake", 1000)
    rec = store_upload(str(tmp_path), "prob-1", up)
    assert rec["stored"] and rec["interpreted"] is False and rec["note"]
    assert (tmp_path / "prob-1" / (rec["sha256"] + ".pdf")).read_bytes() == b"%PDF-1.4 fake"
    assert store_upload(str(tmp_path), "prob-1", up) == rec  # content addressed, repeat is a no-op
    with pytest.raises(ValidationFailed):
        store_upload(str(tmp_path), "../x", up)


# ------------------------------------------------------------------ perception paraphrases
def _roles(text):
    return {n.label: n.role for n in perceive_text(text, "t").problem.graph.nodes}


def test_synonyms_map_unfamiliar_words_to_roles_and_keep_user_wording():
    r = _roles("The vendor delivers the silo. The silo feeds the grinder. The supervisor controls the grinder.")
    assert r["silo"] == "buffer" and r["grinder"] == "transformer" and r["supervisor"] == "controller" and r["vendor"] == "source"


def test_plurals_and_case_are_normalised():
    r = _roles("The Boilers heat the water. The Thermocouples measure the boilers.")
    assert r["boiler"] == "transformer" and r["thermocouple"] == "sensor"
    assert _roles("The valves control the pipelines.")["pipeline"] == "conduit"


def test_unknown_word_still_has_no_role():
    assert _roles("The frobnicator feeds the tank.").get("frobnicator") in (None,)
