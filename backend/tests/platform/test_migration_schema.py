"""Checks the initial migration against docs/database-design.md. Runs with the stdlib only (stubs SQLAlchemy and
Alembic when they are not installed, because only the TABLES data is inspected)."""
import importlib.util
import os
import re
import sys
import types

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MIGRATION = os.path.join(ROOT, "backend", "migrations", "versions", "0001_initial.py")
DOC = os.path.join(ROOT, "docs", "database-design.md")
EXTRA_TABLES = {"pipeline_stages", "reports", "user_settings"}


def _load_migration():
    saved = {k: sys.modules.get(k) for k in ("sqlalchemy", "sqlalchemy.dialects", "alembic")}
    try:
        try:
            import sqlalchemy  # noqa: F401
            import alembic  # noqa: F401
        except ImportError:
            stub = types.ModuleType("sqlalchemy")
            dialects = types.ModuleType("sqlalchemy.dialects")
            dialects.postgresql = types.ModuleType("postgresql")
            stub.dialects = dialects
            al = types.ModuleType("alembic")
            al.op = object()
            sys.modules.update({"sqlalchemy": stub, "sqlalchemy.dialects": dialects,
                                "sqlalchemy.dialects.postgresql": dialects.postgresql, "alembic": al})
        spec = importlib.util.spec_from_file_location("mig0001", MIGRATION)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _split_top(s):
    parts, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def _doc_tables():
    text = open(DOC).read()
    out = {}
    for m in re.finditer(r"### `(\w+)`\nColumns: (.*)", text):
        cols = []
        for item in _split_top(m.group(2).rstrip(".")):
            name = item.split()[0]
            if name in ("unique(project_id,user_id)",) or name.startswith(("unique", "index")):
                continue
            cols.append(name)
        out[m.group(1)] = cols
    return out


def test_every_documented_table_and_column_is_in_the_migration():
    mig = _load_migration()
    tables = {t[0]: t for t in mig.TABLES}
    doc = _doc_tables()
    assert len(doc) == 35
    missing_tables = set(doc) - set(tables)
    assert not missing_tables, missing_tables
    standard = {"id", "created_at", "updated_at"}
    for name, cols in doc.items():
        have = {c[0] for c in tables[name][2]} | standard
        missing = [c for c in cols if c not in have]
        # documented shorthand: "weight" on system_relationships etc. is present; any gap here is a real omission
        assert not missing, f"{name}: missing columns {missing}"


def test_extra_tables_are_documented_and_foreign_keys_resolve_in_order():
    mig = _load_migration()
    names = [t[0] for t in mig.TABLES]
    assert set(names) - set(_doc_tables()) == EXTRA_TABLES
    assert len(names) == len(set(names))
    seen = set()
    for name, soft, cols, uniques, indexes in mig.TABLES:
        for c in cols:
            fk = c[3]
            if fk:
                assert fk[0] in seen or fk[0] == name, f"{name}.{c[0]} references {fk[0]} before it is created"
                assert fk[1] in ("CASCADE", "RESTRICT", "SET NULL")
        seen.add(name)


def test_enums_cover_documented_values():
    mig = _load_migration()
    assert mig.ENUMS["provenance"] == ("source", "computation", "user", "ai_hypothesis")
    assert mig.ENUMS["member_role"] == ("owner", "editor", "viewer")
    assert mig.ENUMS["hypothesis_status"] == ("untested", "supported", "refuted", "inconclusive")
    assert "cancelled" in mig.ENUMS["session_status"]


def test_every_table_with_project_data_has_isolation_column():
    mig = _load_migration()
    tables = {t[0]: {c[0] for c in t[2]} for t in mig.TABLES}
    for name in ("discovery_sessions", "structural_models", "candidate_matches", "structural_mappings", "transformations",
                 "hypotheses", "experiments", "validation_records", "reports", "problems"):
        assert "project_id" in tables[name], name


def test_models_match_migration_when_sqlalchemy_available():
    pytest.importorskip("sqlalchemy")
    pytest.importorskip("alembic")
    from database.base import Base
    import database.models  # noqa: F401
    mig = _load_migration()
    meta = Base.metadata.tables
    assert set(meta) == {t[0] for t in mig.TABLES}
    for name, soft, cols, uniques, indexes in mig.TABLES:
        expect = {"id", "created_at", "updated_at"} | {c[0] for c in cols} | ({"deleted_at"} if soft else set())
        assert set(meta[name].columns.keys()) == expect, name
