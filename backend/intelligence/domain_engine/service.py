"""Domain registry: distance between domains and keyword domain detection."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..fingerprint import tokenize


@dataclass
class Domain:
    id: str
    name: str
    family: str
    description: str
    vocabulary: List[str]


class DomainRegistry:
    def __init__(self, doc: Optional[dict] = None):
        doc = doc or {"domains": [], "family_distance": {}}
        self.domains: Dict[str, Domain] = {d["id"]: Domain(d["id"], d["name"], d["family"], d.get("description", ""),
                                                           list(d.get("vocabulary", []))) for d in doc["domains"]}
        self.family_distance = dict(doc.get("family_distance", {}))

    def get(self, domain_id: str) -> Optional[Domain]:
        return self.domains.get(domain_id)

    def distance(self, a: str, b: str) -> float:
        """0 for the same domain, family based distance otherwise, 1.0 if a domain is unknown."""
        if a == b:
            return 0.0
        da, db = self.domains.get(a), self.domains.get(b)
        if da is None or db is None:
            return 1.0
        key = "-".join(sorted((da.family, db.family)))
        return float(self.family_distance.get(key, 1.0))

    def is_cross_domain(self, a: str, b: str) -> bool:
        return a != b

    def classify_text(self, text: str, top: int = 3) -> List[Tuple[str, float]]:
        """Rank domains by overlap with each domain's vocabulary. Lexical heuristic only."""
        toks = set(tokenize(text))
        stems = {t[:5] for t in toks}
        scored = []
        for d in self.domains.values():
            vocab = {v[:5] for v in d.vocabulary}
            hits = len(stems & vocab)
            if hits:
                scored.append((d.id, hits / max(len(vocab), 1)))
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[:top]

    def detect_domain(self, text: str) -> str:
        ranked = self.classify_text(text, 1)
        return ranked[0][0] if ranked else "unknown"
