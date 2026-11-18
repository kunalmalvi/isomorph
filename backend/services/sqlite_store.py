"""SQLite persistence for runs and hypothesis annotations. Stdlib only.

One database file holds both. Connections are opened per operation (sqlite3 connections are not shared across
threads), WAL mode lets readers proceed while a run writes, and `PRAGMA user_version` records the schema version so
`migrate` can upgrade an older file in place. Migration is idempotent.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Callable, Dict, List, Optional

from .annotations import AnnotationStore
from .run_store import ACTIVE_STATUSES, RunRecord, RunStore

SCHEMA_VERSION = 1

_MIGRATIONS = {
    1: """
    CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        data TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_runs_status ON runs(status);
    CREATE INDEX IF NOT EXISTS ix_runs_created ON runs(created_at);
    CREATE TABLE IF NOT EXISTS annotations (
        run_id TEXT NOT NULL,
        hypothesis_id TEXT NOT NULL,
        decision TEXT NOT NULL,
        note TEXT NOT NULL,
        updated_at REAL NOT NULL,
        PRIMARY KEY (run_id, hypothesis_id)
    );
    """,
}


class SchemaTooNew(RuntimeError):
    pass


class SqliteDatabase:
    """Path handling, connection factory, migration, integrity check and online backup."""

    def __init__(self, path: str):
        self.path = path
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        self.migrate()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    @contextmanager
    def connection(self):
        conn = self._connect()
        try:
            with conn:  # commit on success, roll back on error
                yield conn
        finally:
            conn.close()

    def schema_version(self) -> int:
        with self.connection() as c:
            return c.execute("PRAGMA user_version").fetchone()[0]

    def migrate(self) -> int:
        conn = self._connect()
        try:
            current = conn.execute("PRAGMA user_version").fetchone()[0]
            if current > SCHEMA_VERSION:
                raise SchemaTooNew(f"database schema {current} is newer than this program supports ({SCHEMA_VERSION})")
            for v in range(current + 1, SCHEMA_VERSION + 1):
                conn.executescript("BEGIN;" + _MIGRATIONS[v] + f"PRAGMA user_version={v};COMMIT;")
            return SCHEMA_VERSION
        finally:
            conn.close()

    def integrity_ok(self) -> bool:
        with self.connection() as c:
            return c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    def backup_to(self, dest: str) -> str:
        """Consistent copy using SQLite's online backup API. Safe while the server is running."""
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        if os.path.exists(dest):
            raise FileExistsError(dest)
        src = self._connect()
        out = sqlite3.connect(dest)
        try:
            src.backup(out)
        finally:
            out.close()
            src.close()
        return dest

    def restore_from(self, source: str) -> None:
        """Replace the contents of this database with a backup file (validated first)."""
        if not os.path.isfile(source):
            raise FileNotFoundError(source)
        probe = sqlite3.connect(source)
        try:
            try:
                ok = probe.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                names = {r[0] for r in probe.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            except sqlite3.DatabaseError as e:
                raise ValueError(f"not a readable SQLite database: {e}")
            if not ok:
                raise ValueError("backup file failed its integrity check")
            if not {"runs", "annotations"} <= names:
                raise ValueError("file is not an ISOMORPH backup")
            version = probe.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise SchemaTooNew(f"backup schema {version} is newer than this program supports ({SCHEMA_VERSION})")
            dst = self._connect()
            try:
                probe.backup(dst)
            finally:
                dst.close()
        finally:
            probe.close()
        self.migrate()


class SqliteRunStore(RunStore):
    def __init__(self, db: SqliteDatabase):
        self.db = db

    def get(self, run_id: str) -> Optional[RunRecord]:
        with self.db.connection() as c:
            row = c.execute("SELECT data FROM runs WHERE id=?", (run_id,)).fetchone()
        return RunRecord.from_dict(json.loads(row[0])) if row else None

    def save(self, run: RunRecord) -> None:
        title = str((run.input or {}).get("title") or "")
        with self.db.connection() as c:
            c.execute("INSERT INTO runs(id,status,title,created_at,updated_at,data) VALUES(?,?,?,?,?,?) "
                      "ON CONFLICT(id) DO UPDATE SET status=excluded.status,title=excluded.title,"
                      "updated_at=excluded.updated_at,data=excluded.data",
                      (run.id, run.status, title, run.created_at, run.updated_at, json.dumps(run.to_dict(), sort_keys=True)))

    def active_run_ids(self) -> List[str]:
        marks = ",".join("?" * len(ACTIVE_STATUSES))
        with self.db.connection() as c:
            return [r[0] for r in c.execute(f"SELECT id FROM runs WHERE status IN ({marks}) ORDER BY id", ACTIVE_STATUSES)]

    def list_runs(self, limit: int = 20, offset: int = 0, status: Optional[str] = None) -> dict:
        where, args = ("WHERE status=?", [status]) if status else ("", [])
        with self.db.connection() as c:
            total = c.execute(f"SELECT COUNT(*) FROM runs {where}", args).fetchone()[0]
            rows = c.execute(f"SELECT id,status,title,created_at,updated_at FROM runs {where} "
                             "ORDER BY created_at DESC, id LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
        items = [{"id": r[0], "status": r[1], "title": r[2], "created_at": r[3], "updated_at": r[4]} for r in rows]
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    def all_ids(self) -> List[str]:
        with self.db.connection() as c:
            return [r[0] for r in c.execute("SELECT id FROM runs ORDER BY created_at, id")]

    def delete(self, run_id: str) -> bool:
        with self.db.connection() as c:
            n = c.execute("DELETE FROM runs WHERE id=?", (run_id,)).rowcount
            c.execute("DELETE FROM annotations WHERE run_id=?", (run_id,))
        return n > 0


class SqliteAnnotationStore(AnnotationStore):
    """Same interface as the JSON and in-memory annotation stores, kept in the `annotations` table."""

    def __init__(self, db: SqliteDatabase, clock: Callable[[], float] = time.time):
        super().__init__(clock)
        self.db = db

    def _load(self, run_id: str) -> Dict[str, dict]:
        with self.db.connection() as c:
            rows = c.execute("SELECT hypothesis_id,decision,note,updated_at FROM annotations WHERE run_id=?", (run_id,)).fetchall()
        return {r[0]: {"hypothesis_id": r[0], "decision": r[1], "note": r[2], "provenance": "user", "updated_at": r[3]} for r in rows}

    def _write(self, run_id: str, data: Dict[str, dict]) -> None:
        with self.db.connection() as c:
            c.execute("DELETE FROM annotations WHERE run_id=?", (run_id,))
            c.executemany("INSERT INTO annotations(run_id,hypothesis_id,decision,note,updated_at) VALUES(?,?,?,?,?)",
                          [(run_id, h, d["decision"], d["note"], d["updated_at"]) for h, d in data.items()])

    def _run_ids(self) -> list:
        with self.db.connection() as c:
            return sorted(r[0] for r in c.execute("SELECT DISTINCT run_id FROM annotations"))

    def _remove(self, run_id: str) -> None:
        with self.db.connection() as c:
            c.execute("DELETE FROM annotations WHERE run_id=?", (run_id,))
