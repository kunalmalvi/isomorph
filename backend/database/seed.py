"""Load data/ seed knowledge into the knowledge tables (sources, domains, domain_systems, system_entities,
system_relationships, mechanisms). Idempotent: running it twice creates no duplicates. Never run automatically.

Run explicitly: `python -m database.seed --database-url sqlite:///./isomorph.db` (tables must exist, see alembic).
Application startup never calls it.

`plan_seed` and `apply_plan` are stdlib only and tested with an in memory sink. `SqlSink` needs SQLAlchemy and is
UNVERIFIED in the authoring sandbox.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from typing import Dict, Iterable, List, Optional, Protocol, Tuple

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")
SOURCE_TYPES = {"textbook": "book", "paper": "paper", "standard": "standard", "dataset": "dataset"}


def _source_type(kind: str) -> str:
    return SOURCE_TYPES.get(kind, "internal")


def plan_seed(data_dir: Optional[str] = None) -> dict:
    """Read data/ and return rows to insert, with natural keys instead of ids. Pure and deterministic."""
    base = os.path.abspath(data_dir or os.environ.get("ISOMORPH_DATA_DIR") or DEFAULT_DATA_DIR)
    with open(os.path.join(base, "domains", "domains.json")) as f:
        domains = [{"name": d["id"], "description": d.get("description", "")} for d in json.load(f)["domains"]]
    sources: Dict[str, dict] = {}
    systems: List[dict] = []
    mechanisms: List[dict] = []
    for folder in ("seed_knowledge", "mechanisms"):
        for fp in sorted(glob.glob(os.path.join(base, folder, "*.json"))):
            with open(fp) as f:
                doc = json.load(f)
            for s in doc["systems"]:
                refs = []
                for src in s.get("sources", []):
                    sources.setdefault(src["citation"], {"citation": src["citation"], "title": src["citation"][:200],
                                                         "source_type": _source_type(src.get("kind", ""))})
                    refs.append(src["citation"])
                if not refs:
                    sources.setdefault("ISOMORPH seed data", {"citation": "ISOMORPH seed data", "title": "ISOMORPH seed data", "source_type": "internal"})
                    refs = ["ISOMORPH seed data"]
                nodes = {n["id"]: n for n in s["graph"]["nodes"]}
                systems.append({"key": s["id"], "domain": s["domain"], "name": s["name"], "description": s.get("summary", ""),
                                "source": refs[0],
                                "entities": [{"key": n["id"], "name": n["label"], "kind": n.get("kind"), "role": n.get("role")}
                                             for n in nodes.values()],
                                "relationships": [{"key": e["id"], "source": e["source"], "target": e["target"],
                                                   "relation_type": e["relation"], "weight": e.get("weight")}
                                                  for e in s["graph"]["edges"] if e["source"] in nodes and e["target"] in nodes]})
                if folder == "mechanisms":
                    mechanisms.append({"system": s["id"], "name": s["name"], "description": s.get("summary", ""),
                                       "function_tag": s.get("kind"), "source": refs[0]})
    return {"domains": domains, "sources": sorted(sources.values(), key=lambda x: x["citation"]),
            "systems": sorted(systems, key=lambda x: x["key"]), "mechanisms": sorted(mechanisms, key=lambda x: x["system"])}


class Sink(Protocol):
    def ensure(self, table: str, key: Tuple, values: dict) -> Tuple[object, bool]:
        """Return (id, created). Must not create a second row for an existing natural key."""


def apply_plan(plan: dict, sink: Sink) -> Dict[str, int]:
    """Insert the plan through a sink. Returns the number of rows created per table (all zero on a second run)."""
    created: Dict[str, int] = {t: 0 for t in ("domains", "sources", "domain_systems", "system_entities", "system_relationships", "mechanisms")}

    def ensure(table, key, values):
        rid, new = sink.ensure(table, key, values)
        created[table] += int(new)
        return rid

    dom = {d["name"]: ensure("domains", (d["name"],), {"name": d["name"], "description": d["description"]}) for d in plan["domains"]}
    src = {s["citation"]: ensure("sources", (s["citation"],), {"citation": s["citation"], "title": s["title"], "source_type": s["source_type"]})
           for s in plan["sources"]}
    sys_ids: Dict[str, object] = {}
    for s in plan["systems"]:
        if s["domain"] not in dom:
            dom[s["domain"]] = ensure("domains", (s["domain"],), {"name": s["domain"], "description": ""})
        sid = sys_ids[s["key"]] = ensure("domain_systems", (dom[s["domain"]], s["name"]),
                                         {"domain_id": dom[s["domain"]], "name": s["name"], "description": s["description"],
                                          "source_id": src[s["source"]], "provenance": "source"})
        ents = {e["key"]: ensure("system_entities", (sid, e["name"]), {"domain_system_id": sid, "name": e["name"], "kind": e["kind"], "role": e["role"]})
                for e in s["entities"]}
        for r in s["relationships"]:
            ensure("system_relationships", (sid, ents[r["source"]], ents[r["target"]], r["relation_type"]),
                   {"domain_system_id": sid, "source_entity_id": ents[r["source"]], "target_entity_id": ents[r["target"]],
                    "relation_type": r["relation_type"], "weight": r["weight"]})
    for m in plan["mechanisms"]:
        ensure("mechanisms", (sys_ids[m["system"]], m["name"]),
               {"domain_system_id": sys_ids[m["system"]], "name": m["name"], "description": m["description"],
                "function_tag": m["function_tag"], "source_id": src[m["source"]], "provenance": "source"})
    return created


class MemorySink:
    """Dictionary backed sink used by tests and dry runs."""

    def __init__(self):
        self.rows: Dict[str, Dict[Tuple, dict]] = {}

    def ensure(self, table, key, values):
        t = self.rows.setdefault(table, {})
        if key in t:
            return t[key]["id"], False
        t[key] = dict(values, id=f"{table}:{len(t) + 1}")
        return t[key]["id"], True


class SqlSink:
    """SQLAlchemy sink: looks a row up by its natural key and inserts it only when absent. UNVERIFIED in the sandbox."""

    def __init__(self, session):
        from database import models as m
        self.s = session
        self.models = {"domains": (m.Domain, ("name",)), "sources": (m.Source, ("citation",)),
                       "domain_systems": (m.DomainSystem, ("domain_id", "name")),
                       "system_entities": (m.SystemEntity, ("domain_system_id", "name")),
                       "system_relationships": (m.SystemRelationship, ("domain_system_id", "source_entity_id", "target_entity_id", "relation_type")),
                       "mechanisms": (m.Mechanism, ("domain_system_id", "name"))}

    def ensure(self, table, key, values):
        from sqlalchemy import select
        model, cols = self.models[table]
        stmt = select(model)
        for c, v in zip(cols, key):
            stmt = stmt.where(getattr(model, c) == v)
        row = self.s.execute(stmt).scalars().first()
        if row is not None:
            return row.id, False
        row = model(**values)
        self.s.add(row)
        self.s.flush()
        return row.id, True


def seed_database(session_factory, data_dir: Optional[str] = None) -> Dict[str, int]:
    plan = plan_seed(data_dir)
    with session_factory() as db:
        created = apply_plan(plan, SqlSink(db))
        db.commit()
    return created


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Seed the knowledge tables from data/. Idempotent.")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL", "sqlite:///./isomorph.db"))
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--dry-run", action="store_true", help="print the row counts that would be created without a database")
    a = ap.parse_args(list(argv) if argv is not None else None)
    if a.dry_run:
        print(json.dumps(apply_plan(plan_seed(a.data_dir), MemorySink()), sort_keys=True))
        return 0
    from database.session import make_engine, make_session_factory
    print(json.dumps(seed_database(make_session_factory(make_engine(a.database_url)), a.data_dir), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
