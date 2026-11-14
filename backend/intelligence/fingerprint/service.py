"""Structural DNA fingerprint (versioned).

Layout for FINGERPRINT_VERSION 1 (fixed lengths):
- functional  (len(ROLES) + len(BEHAVIOUR_TAGS)): role distribution then behaviour indicators
- relational  (len(RELATIONS)+1 + 16): relation-type distribution (+unclassified) then 16 hashed bins of
              (source role, relation, target role) triple distribution
- topological (12): normalized graph features
- dynamic     (len(DYNAMICS_TAGS)): indicator vector
- constraint  (len(CONSTRAINT_TAGS)): indicator vector
- semantic    (64): hashed TF-IDF style bag of words. LEXICAL, NOT NEURAL: it captures shared words,
              not meaning.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Dict, List, Optional, Sequence

from ..schemas import (Fingerprint, ROLES, RELATIONS, UNCLASSIFIED, DYNAMICS_TAGS, CONSTRAINT_TAGS,
                       BEHAVIOUR_TAGS)
from ..structural_model import StructuralModel

FINGERPRINT_VERSION = 1
SEMANTIC_DIM = 64
TRIPLE_BINS = 16
REL_ORDER = tuple(sorted(RELATIONS)) + (UNCLASSIFIED,)
STOPWORDS = frozenset("a an the of and or to in on for with by is are be as at from that this it its into "
                      "than then which when while".split())


def stable_bucket(token: str, dim: int) -> int:
    return int(hashlib.sha256(token.encode()).hexdigest()[:8], 16) % dim


def tokenize(text: str) -> List[str]:
    toks = re.findall(r"[a-z][a-z0-9]+", text.lower())
    return [t for t in toks if t not in STOPWORDS and len(t) > 2]


def semantic_embedding(text: str, idf: Optional[Dict[str, float]] = None, dim: int = SEMANTIC_DIM) -> List[float]:
    """Deterministic hashed bag-of-words with sublinear tf and optional idf, L2 normalized.

    LEXICAL similarity only. It does not understand synonyms or meaning.
    """
    vec = [0.0] * dim
    tf: Dict[str, int] = {}
    for t in tokenize(text):
        tf[t] = tf.get(t, 0) + 1
    for t, c in tf.items():
        w = (1.0 + math.log(c)) * (idf.get(t, 1.0) if idf else 1.0)
        # signed hashing reduces collision bias
        sign = 1.0 if int(hashlib.sha256(("s" + t).encode()).hexdigest()[:2], 16) % 2 == 0 else -1.0
        vec[stable_bucket(t, dim)] += sign * w
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


def build_idf(texts: Sequence[str]) -> Dict[str, float]:
    df: Dict[str, int] = {}
    for t in texts:
        for tok in set(tokenize(t)):
            df[tok] = df.get(tok, 0) + 1
    n = len(texts)
    return {k: math.log((1 + n) / (1 + v)) + 1.0 for k, v in df.items()}


def _normalize_counts(counts: Dict[str, float], order: Sequence[str]) -> List[float]:
    tot = sum(counts.values())
    return [counts.get(k, 0.0) / tot if tot else 0.0 for k in order]


def triple_patterns(model: StructuralModel) -> Dict[tuple, int]:
    roles = {n.id: (n.role or "none") for n in model.graph.nodes}
    out: Dict[tuple, int] = {}
    for e in model.graph.edges:
        k = (roles.get(e.source, "none"), e.relation, roles.get(e.target, "none"))
        out[k] = out.get(k, 0) + 1
    return out


def topological_features(model: StructuralModel) -> List[float]:
    """12 features in [0,1]. A single-node graph yields all zeros."""
    m = model.metrics
    n = m["node_count"]
    if n <= 1:
        return [0.0] * 12
    e = m["edge_count"]
    mo = m["motifs"]
    sat = lambda x, k: x / (x + k)  # saturating map to [0,1)
    return [
        sat(n, 8.0), sat(e, 10.0), m["density"], sat(m["mean_degree"], 3.0),
        sat(m["max_out_degree"], 3.0), sat(m["max_in_degree"], 3.0),
        sat(m["cycle_count"], 3.0), sat(m["negative_loops"], 2.0), sat(m["positive_loops"], 2.0),
        sat(m["depth"], 4.0), m["max_betweenness"], sat(mo["feed_forward_loop"] + mo["bi_fan"], 2.0),
    ]


def compute_fingerprint(model: StructuralModel, idf: Optional[Dict[str, float]] = None) -> Fingerprint:
    functional = _normalize_counts({k: float(v) for k, v in model.role_counts.items()}, ROLES) + \
        [1.0 if b in model.behaviours else 0.0 for b in BEHAVIOUR_TAGS]
    rel_counts: Dict[str, float] = {}
    for e in model.graph.edges:
        rel_counts[e.relation] = rel_counts.get(e.relation, 0.0) + 1.0
    bins: Dict[str, float] = {}
    for k, c in triple_patterns(model).items():
        b = str(stable_bucket("|".join(k), TRIPLE_BINS))
        bins[b] = bins.get(b, 0.0) + c
    relational = _normalize_counts(rel_counts, REL_ORDER) + _normalize_counts(bins, [str(i) for i in range(TRIPLE_BINS)])
    topological = topological_features(model)
    dynamic = [1.0 if t in model.dynamics else 0.0 for t in DYNAMICS_TAGS]
    constraint = [1.0 if t in model.constraint_tags else 0.0 for t in CONSTRAINT_TAGS]
    semantic = semantic_embedding(model.text, idf)
    # round floats for a platform-stable hash
    payload = json.dumps([FINGERPRINT_VERSION] + [[round(x, 6) for x in v] for v in
                         (functional, relational, topological, dynamic, constraint, semantic)],
                         separators=(",", ":"))
    h = hashlib.sha256(payload.encode()).hexdigest()
    return Fingerprint(FINGERPRINT_VERSION, functional, relational, topological, dynamic, constraint, semantic, h)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return max(0.0, min(1.0, sum(x * y for x, y in zip(a, b)) / (na * nb)))


def closeness(a: Sequence[float], b: Sequence[float]) -> float:
    """1 - mean absolute difference, for bounded feature vectors."""
    if not a:
        return 0.0
    return 1.0 - sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def jaccard(a: Sequence, b: Sequence) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def vector_similarity(a: Fingerprint, b: Fingerprint) -> float:
    """Cheap whole-fingerprint similarity used only for candidate retrieval (stage 1)."""
    parts = [cosine(a.functional, b.functional), cosine(a.relational, b.relational),
             closeness(a.topological, b.topological), jaccard_vec(a.dynamic, b.dynamic),
             jaccard_vec(a.constraint, b.constraint)]
    return sum(parts) / len(parts)


def jaccard_vec(a: Sequence[float], b: Sequence[float]) -> float:
    inter = sum(1 for x, y in zip(a, b) if x > 0 and y > 0)
    union = sum(1 for x, y in zip(a, b) if x > 0 or y > 0)
    return inter / union if union else 0.0
