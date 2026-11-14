"""Server side hypothesis decisions and notes, scoped to a discovery run. Stdlib only.

An annotation is the reviewer's own judgement about a generated hypothesis (shortlist, reject, promote, free note).
It always has provenance "user" and never changes the hypothesis text or validation outcome.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import time
from typing import Callable, Dict, Optional

from core.errors import ValidationFailed

DECISIONS = ("none", "saved", "rejected", "promoted")
MAX_NOTE_CHARS = 5000
_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:")


def validate_annotation(hypothesis_id: str, decision: str, note: str) -> None:
    if not hypothesis_id or len(hypothesis_id) > 128 or any(c not in _ID_CHARS for c in hypothesis_id):
        raise ValidationFailed("invalid hypothesis id")
    if decision not in DECISIONS:
        raise ValidationFailed(f"decision must be one of {list(DECISIONS)}")
    if not isinstance(note, str) or len(note) > MAX_NOTE_CHARS:
        raise ValidationFailed(f"note must be a string of at most {MAX_NOTE_CHARS} characters")


class AnnotationStore:
    def __init__(self, clock: Callable[[], float] = time.time):
        self.clock = clock
        self._lock = threading.Lock()

    def _load(self, run_id: str) -> Dict[str, dict]:
        raise NotImplementedError

    def _write(self, run_id: str, data: Dict[str, dict]) -> None:
        raise NotImplementedError

    def list(self, run_id: str) -> Dict[str, dict]:
        with self._lock:
            return copy.deepcopy(self._load(run_id))

    def set(self, run_id: str, hypothesis_id: str, decision: str = "none", note: str = "") -> dict:
        validate_annotation(hypothesis_id, decision, note)
        with self._lock:
            data = self._load(run_id)
            rec = {"hypothesis_id": hypothesis_id, "decision": decision, "note": note, "provenance": "user",
                   "updated_at": self.clock()}
            data[hypothesis_id] = rec
            self._write(run_id, data)
            return dict(rec)

    def delete(self, run_id: str, hypothesis_id: str) -> bool:
        with self._lock:
            data = self._load(run_id)
            existed = data.pop(hypothesis_id, None) is not None
            if existed:
                self._write(run_id, data)
            return existed


class InMemoryAnnotationStore(AnnotationStore):
    def __init__(self, clock: Callable[[], float] = time.time):
        super().__init__(clock)
        self._data: Dict[str, Dict[str, dict]] = {}

    def _load(self, run_id):
        return self._data.setdefault(run_id, {})

    def _write(self, run_id, data):
        self._data[run_id] = data


class JsonFileAnnotationStore(AnnotationStore):
    """One JSON file per run, written atomically. Survives restarts.

    Single process only. The lock is in process and each update reads and rewrites the whole file, so two API
    processes sharing the directory can lose each other's updates. Move to a database table before scaling out.
    Files are kept when a discovery is soft deleted; the API hides notes for hypotheses that no longer exist.
    """

    def __init__(self, directory: str, clock: Callable[[], float] = time.time):
        super().__init__(clock)
        self.dir = directory
        os.makedirs(directory, exist_ok=True)

    def _path(self, run_id: str) -> str:
        if not run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in run_id):
            raise ValueError("invalid run id")
        return os.path.join(self.dir, run_id + ".annotations.json")

    def _load(self, run_id):
        p = self._path(run_id)
        if not os.path.exists(p):
            return {}
        with open(p) as f:
            return json.load(f)

    def _write(self, run_id, data):
        p = self._path(run_id)
        fd, tmp = tempfile.mkstemp(dir=self.dir, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, sort_keys=True)
        os.replace(tmp, p)
