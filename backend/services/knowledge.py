"""Seed knowledge access and cached analogy engines. Stdlib only."""
from __future__ import annotations

import threading
from typing import Dict, List, Optional, Tuple

from intelligence.analogy_engine import AnalogyEngine
from intelligence.domain_engine import DomainRegistry
from intelligence.schemas import ScoreWeights, System
from knowledge_base import load_domains, load_systems


class KnowledgeBase:
    def __init__(self, data_dir: Optional[str] = None, systems: Optional[List[System]] = None, domains_doc: Optional[dict] = None):
        self.domains_doc = domains_doc if domains_doc is not None else load_domains(data_dir)
        self.systems: List[System] = systems if systems is not None else load_systems(data_dir)
        self.registry = DomainRegistry(self.domains_doc)
        self.by_id: Dict[str, System] = {s.id: s for s in self.systems}
        self.mechanism_ids = (set(self.by_id) - {s.id for s in load_systems(data_dir, include_mechanisms=False)}
                              if systems is None else set())
        self._engines: Dict[Tuple, AnalogyEngine] = {}
        self._lock = threading.Lock()

    def engine(self, weights: Optional[ScoreWeights] = None) -> AnalogyEngine:
        w = weights or ScoreWeights()
        w.validate()
        key = tuple(sorted(w.to_dict().items()))
        with self._lock:
            if key not in self._engines:
                self._engines[key] = AnalogyEngine(self.systems, self.registry, w)
            return self._engines[key]


_default: Dict[Optional[str], KnowledgeBase] = {}
_default_lock = threading.Lock()


def default_knowledge(data_dir: Optional[str] = None) -> KnowledgeBase:
    with _default_lock:
        if data_dir not in _default:
            _default[data_dir] = KnowledgeBase(data_dir)
        return _default[data_dir]
