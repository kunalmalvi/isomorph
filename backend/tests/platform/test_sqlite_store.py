import os
import sqlite3
import threading

import pytest

from core.errors import ValidationFailed
from services.orchestrator import Orchestrator, STAGES
from services.run_store import RunRecord, StageRecord
from services.sqlite_store import SCHEMA_VERSION, SchemaTooNew, SqliteAnnotationStore, SqliteDatabase, SqliteRunStore


def _run(i="r1", status="queued"):
    return RunRecord(i, {"text": "x", "problem": None, "title": "T " + i}, {}, status, None, {n: StageRecord(n) for n in STAGES}, 1.0, 2.0)


def test_run_roundtrip_and_restart(tmp_path):
    p = str(tmp_path / "a.db")
    s = SqliteRunStore(SqliteDatabase(p))
    s.save(_run("r1"))
    r = _run("r1", "done")
    r.stages["perception"].output = {"k": [1, 2]}
    s.save(r)  # upsert
    s2 = SqliteRunStore(SqliteDatabase(p))  # new connection objects, same file
    got = s2.get("r1")
    assert got.status == "done" and got.stages["perception"].output == {"k": [1, 2]}
    assert s2.get("missing") is None


def test_active_and_list_and_delete(tmp_path):
    db = SqliteDatabase(str(tmp_path / "a.db"))
    s, a = SqliteRunStore(db), SqliteAnnotationStore(db)
    for i, st in (("a", "queued"), ("b", "running"), ("c", "done")):
        s.save(_run(i, st))
    assert s.active_run_ids() == ["a", "b"]
    page = s.list_runs(limit=2, offset=0)
    assert page["total"] == 3 and len(page["items"]) == 2
    assert s.list_runs(status="done")["total"] == 1
    a.set("c", "H1-x", "saved", "n")
    assert s.delete("c") is True and s.delete("c") is False
    assert a.list("c") == {}


def test_annotations_persist_and_validate(tmp_path):
    p = str(tmp_path / "a.db")
    a = SqliteAnnotationStore(SqliteDatabase(p))
    a.set("r1", "H1-x", "saved", "good")
    a.set("r1", "H2-y", "rejected")
    assert SqliteAnnotationStore(SqliteDatabase(p)).list("r1")["H1-x"]["note"] == "good"
    with pytest.raises(ValidationFailed):
        a.set("r1", "H1-x", "bogus")
    assert a.delete("r1", "H2-y") and not a.delete("r1", "H2-y")
    assert a.purge_run("r1") and a.list("r1") == {}
    a.set("r2", "H1-x", "saved")
    assert a.safe_cleanup_orphans([]) == []
    assert a.cleanup_orphans(["other"]) == ["r2"]


def test_migration_idempotent_and_versioned(tmp_path):
    p = str(tmp_path / "a.db")
    db = SqliteDatabase(p)
    assert db.schema_version() == SCHEMA_VERSION
    assert db.migrate() == SCHEMA_VERSION and db.migrate() == SCHEMA_VERSION
    assert db.integrity_ok()
    with sqlite3.connect(p) as c:
        assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        c.execute(f"PRAGMA user_version={SCHEMA_VERSION + 5}")
    with pytest.raises(SchemaTooNew):
        SqliteDatabase(p)


def test_concurrent_writes(tmp_path):
    db = SqliteDatabase(str(tmp_path / "a.db"))
    s = SqliteRunStore(db)
    errs = []

    def work(k):
        try:
            for i in range(15):
                s.save(_run(f"t{k}-{i}"))
        except Exception as e:  # pragma: no cover
            errs.append(e)
    ts = [threading.Thread(target=work, args=(k,)) for k in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs and s.list_runs(limit=100)["total"] == 90


def test_backup_and_restore(tmp_path):
    db = SqliteDatabase(str(tmp_path / "a.db"))
    s = SqliteRunStore(db)
    s.save(_run("keep"))
    b = db.backup_to(str(tmp_path / "bk" / "b.db"))
    with pytest.raises(FileExistsError):
        db.backup_to(b)
    s.save(_run("later"))
    db.restore_from(b)
    assert s.get("keep") is not None and s.get("later") is None
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"not a database at all")
    with pytest.raises(ValueError):
        db.restore_from(str(bad))
    assert s.get("keep") is not None  # failed restore left data intact
    other = tmp_path / "other.db"
    with sqlite3.connect(other) as c:
        c.execute("CREATE TABLE t(x)")
    with pytest.raises(ValueError):
        db.restore_from(str(other))


def test_orchestrator_runs_on_sqlite(tmp_path):
    s = SqliteRunStore(SqliteDatabase(str(tmp_path / "a.db")))
    o = Orchestrator(s)
    run = o.create_run(text="A pump moves fluid. The pipe constrains the fluid. Friction dissipates energy. The goal is to reduce energy loss.")
    assert o.run(run.id).status == "done"
    assert s.get(run.id).stages["validation"].status == "done"
