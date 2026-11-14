"""Run and stage records plus persistence backends (in memory, JSON file). Stdlib only.

The SQLAlchemy backed store lives in api/db_store.py and implements the same `RunStore` interface.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

STAGE_STATUSES = ("pending", "running", "done", "failed", "stale", "skipped")
ACTIVE_STATUSES = ("queued", "running")
RUN_STATUSES = ("queued", "running", "done", "failed", "cancelled")


@dataclass
class StageRecord:
    name: str
    status: str = "pending"
    output: Optional[dict] = None
    error: Optional[str] = None
    source: str = "computation"  # computation | user | ai_hypothesis
    version: int = 0
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    def to_dict(self, include_output: bool = True) -> dict:
        d = {"name": self.name, "status": self.status, "error": self.error, "source": self.source,
             "version": self.version, "started_at": self.started_at, "finished_at": self.finished_at}
        if include_output:
            d["output"] = self.output
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "StageRecord":
        return cls(d["name"], d.get("status", "pending"), d.get("output"), d.get("error"), d.get("source", "computation"),
                   int(d.get("version", 0)), d.get("started_at"), d.get("finished_at"))


@dataclass
class RunRecord:
    id: str
    input: dict
    config: dict
    status: str = "queued"
    error: Optional[str] = None
    stages: Dict[str, StageRecord] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self, include_output: bool = True) -> dict:
        return {"id": self.id, "input": self.input, "config": self.config, "status": self.status, "error": self.error,
                "stages": [s.to_dict(include_output) for s in self.stages.values()],
                "created_at": self.created_at, "updated_at": self.updated_at}

    @classmethod
    def from_dict(cls, d: dict) -> "RunRecord":
        st = {s["name"]: StageRecord.from_dict(s) for s in d.get("stages", [])}
        return cls(d["id"], d["input"], d["config"], d.get("status", "queued"), d.get("error"), st,
                   d.get("created_at", 0.0), d.get("updated_at", 0.0))

    def progress(self) -> dict:
        """Small snapshot used by the SSE endpoint."""
        stages = list(self.stages.values())
        done = sum(1 for s in stages if s.status == "done")
        return {"run_id": self.id, "status": self.status, "completed": done, "total": len(stages), "error": self.error,
                "stages": [{"name": s.name, "status": s.status, "version": s.version, "source": s.source} for s in stages]}


class RunStore:
    def get(self, run_id: str) -> Optional[RunRecord]:
        raise NotImplementedError

    def save(self, run: RunRecord) -> None:
        raise NotImplementedError

    def active_run_ids(self) -> List[str]:
        """Ids of runs whose status is queued or running. Used for restart recovery."""
        raise NotImplementedError


class InMemoryRunStore(RunStore):
    """Stores deep copies so callers cannot mutate persisted state by accident."""

    def __init__(self):
        self._runs: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def get(self, run_id):
        with self._lock:
            d = self._runs.get(run_id)
            return RunRecord.from_dict(copy.deepcopy(d)) if d is not None else None

    def save(self, run):
        with self._lock:
            self._runs[run.id] = copy.deepcopy(run.to_dict())

    def active_run_ids(self):
        with self._lock:
            return sorted(i for i, d in self._runs.items() if d.get("status") in ACTIVE_STATUSES)


class JsonFileRunStore(RunStore):
    """One JSON file per run, written atomically. Survives process restarts."""

    def __init__(self, directory: str):
        self.dir = directory
        os.makedirs(directory, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, run_id: str) -> str:
        if not run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in run_id):
            raise ValueError("invalid run id")
        return os.path.join(self.dir, run_id + ".json")

    def get(self, run_id):
        p = self._path(run_id)
        with self._lock:
            if not os.path.exists(p):
                return None
            with open(p) as f:
                return RunRecord.from_dict(json.load(f))

    def save(self, run):
        p = self._path(run.id)
        with self._lock:
            fd, tmp = tempfile.mkstemp(dir=self.dir, suffix=".tmp")
            with os.fdopen(fd, "w") as f:
                json.dump(run.to_dict(), f, sort_keys=True)
            os.replace(tmp, p)

    def active_run_ids(self):
        out = []
        with self._lock:
            for name in sorted(os.listdir(self.dir)):
                if not name.endswith(".json") or name.endswith(".annotations.json"):
                    continue
                try:
                    with open(os.path.join(self.dir, name)) as f:
                        d = json.load(f)
                except (OSError, ValueError):
                    continue
                if d.get("status") in ACTIVE_STATUSES:
                    out.append(d["id"])
        return out
