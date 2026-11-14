"""Learning memory: JSON or in-memory store of what worked, with evidence levels and conditions.

Evidence levels (low to high): none, simulation, expert_review, real_world. A simulation outcome can never
be stored above 'simulation' by `record_validation`. Records are versioned: re-recording the same key and
conditions appends a new version and keeps history. Time is injected (no hidden clock) so tests are reproducible.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from ..schemas import Hypothesis, Validation

EVIDENCE_LEVELS = ("none", "simulation", "expert_review", "real_world")


class MemoryStore:
    def __init__(self, path: Optional[str] = None):
        self.path = path
        self.records: List[dict] = []
        if path and os.path.exists(path):
            with open(path) as f:
                self.records = json.load(f)["records"]

    def _next_id(self) -> str:
        return f"mem-{len(self.records) + 1}"

    def add(self, key: str, outcome: str, evidence_level: str = "simulation", conditions: Optional[dict] = None,
            payload: Optional[dict] = None, tags: Optional[List[str]] = None, timestamp: int = 0) -> dict:
        if evidence_level not in EVIDENCE_LEVELS:
            raise ValueError(f"evidence_level must be one of {EVIDENCE_LEVELS}")
        conditions = dict(conditions or {})
        version = 1 + max([r["version"] for r in self.records if r["key"] == key and r["conditions"] == conditions] or [0])
        rec = {"id": self._next_id(), "key": key, "outcome": outcome, "evidence_level": evidence_level,
               "conditions": conditions, "payload": payload or {}, "tags": sorted(tags or []), "version": version,
               "timestamp": timestamp}
        self.records.append(rec)
        return rec

    def record_validation(self, h: Hypothesis, v: Validation, concept_type: str, conditions: Optional[dict] = None,
                          timestamp: int = 0) -> dict:
        """Store a validation. Level is capped at 'simulation'; 'untested' is stored with level 'none'."""
        level = "none" if v.outcome == "untested" else "simulation"
        return self.add(f"strategy:{concept_type}", v.outcome, level, conditions,
                        {"hypothesis_id": h.id, "category": h.category, "evidence": v.evidence}, [concept_type, h.category], timestamp)

    def record_feedback(self, key: str, helpful: bool, conditions: Optional[dict] = None, timestamp: int = 0) -> dict:
        """User feedback on a match or concept. Stored as expert_review level evidence of usefulness only."""
        return self.add(key, "helpful" if helpful else "not_helpful", "expert_review", conditions, {}, ["feedback"], timestamp)

    def latest(self, key: str, conditions: Optional[dict] = None) -> Optional[dict]:
        rs = [r for r in self.records if r["key"] == key and (conditions is None or r["conditions"] == conditions)]
        return max(rs, key=lambda r: (r["version"], r["timestamp"], r["id"])) if rs else None

    def history(self, key: str, conditions: Optional[dict] = None) -> List[dict]:
        return sorted((r for r in self.records if r["key"] == key and (conditions is None or r["conditions"] == conditions)),
                      key=lambda r: (r["version"], r["id"]))

    def retrieve(self, key_prefix: str = "", conditions: Optional[dict] = None, limit: int = 10) -> List[dict]:
        """Records whose key starts with prefix and whose conditions contain all requested items.
        Ranked by evidence level, then version, then id (stable)."""
        want = conditions or {}
        out = [r for r in self.records if r["key"].startswith(key_prefix) and all(r["conditions"].get(k) == v for k, v in want.items())]
        out.sort(key=lambda r: (-EVIDENCE_LEVELS.index(r["evidence_level"]), -r["version"], r["id"]))
        return out[:limit]

    def strategy_stats(self, concept_type: str) -> Dict[str, int]:
        stats = {"supported": 0, "refuted": 0, "inconclusive": 0, "untested": 0}
        for r in self.records:
            if r["key"] == f"strategy:{concept_type}" and r["outcome"] in stats:
                stats[r["outcome"]] += 1
        return stats

    def prior_adjustment(self, concept_type: str) -> float:
        """Small ranking nudge in [-0.1, 0.1] from past simulation outcomes. Never overrides scoring evidence."""
        s = self.strategy_stats(concept_type)
        n = s["supported"] + s["refuted"] + s["inconclusive"]
        if n == 0:
            return 0.0
        return round(0.1 * (s["supported"] - s["refuted"]) / n, 6)

    def save(self, path: Optional[str] = None) -> None:
        p = path or self.path
        if not p:
            raise ValueError("no path configured")
        with open(p, "w") as f:
            json.dump({"schema_version": 1, "records": self.records}, f, indent=1, sort_keys=True)
