"""Role- and relation-constrained mapping between two typed graphs.

Method (similarity flooding style, deterministic):
1. Candidate pairs only where roles are compatible (equal role 1.0, same role family 0.5, missing role 0.3).
2. Iteratively refine pair score S(a,b) = compat(a,b) * (0.25 + 0.75 * N(a,b)) where N is the mean of an
   out-neighbourhood and an in-neighbourhood term. For each incident edge of a the best matching edge of b is
   found (relation equal 1.0, different relation with same sign 0.3, otherwise 0), weighted by the current score
   of the neighbour pair, summed and divided by max(degree(a), degree(b)). Nodes with equal (zero) degree match
   fully on that side. Scores are damped with the previous round.
3. Greedy one-to-one assignment by descending score (ties by ids). Mapping is injective.
4. Edges: preserved (same relation between mapped endpoints), modified (different relation or reversed
   direction), lost (source edge with no counterpart or unmapped endpoint).

Confidence = 0.3 * mean node pair score + 0.4 * weighted edge recall + 0.3 * node coverage of the source graph.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..schemas import Graph, ROLE_FAMILIES, RELATIONS

CONFIDENCE_FORMULA = ("confidence = 0.3*mean_pair_score + 0.4*weighted_edge_recall + 0.3*node_coverage "
                      "(preserved edge = 1.0, modified same sign = 0.4, modified other = 0.2)")
MIN_PAIR_SCORE = 0.2


def role_compat(ra: Optional[str], rb: Optional[str]) -> float:
    if ra is None or rb is None:
        return 0.3
    if ra == rb:
        return 1.0
    if ROLE_FAMILIES.get(ra) is not None and ROLE_FAMILIES.get(ra) == ROLE_FAMILIES.get(rb):
        return 0.5
    return 0.0


def relation_compat(ra: str, rb: str) -> float:
    if ra == rb:
        return 1.0
    if ra in RELATIONS and rb in RELATIONS and RELATIONS[ra] == RELATIONS[rb]:
        return 0.3
    return 0.0


@dataclass
class Mapping:
    node_pairs: List[Tuple[str, str, float]] = field(default_factory=list)
    edge_pairs: List[dict] = field(default_factory=list)  # preserved and modified
    lost_edges: List[dict] = field(default_factory=list)
    unmatched_target_edges: List[str] = field(default_factory=list)
    unmapped_source: List[str] = field(default_factory=list)
    unmapped_target: List[str] = field(default_factory=list)
    confidence: float = 0.0
    edge_recall: float = 0.0
    edge_precision: float = 0.0
    edge_f1: float = 0.0
    node_coverage: float = 0.0
    mean_pair_score: float = 0.0
    formula: str = CONFIDENCE_FORMULA

    @property
    def preserved(self) -> List[dict]:
        return [e for e in self.edge_pairs if e["status"] == "preserved"]

    @property
    def modified(self) -> List[dict]:
        return [e for e in self.edge_pairs if e["status"] == "modified"]

    def pair_dict(self) -> Dict[str, str]:
        return {s: t for s, t, _ in self.node_pairs}

    def to_dict(self) -> dict:
        return {"node_pairs": [list(p) for p in self.node_pairs], "edge_pairs": self.edge_pairs,
                "lost_edges": self.lost_edges, "unmatched_target_edges": self.unmatched_target_edges,
                "unmapped_source": self.unmapped_source, "unmapped_target": self.unmapped_target,
                "confidence": self.confidence, "edge_recall": self.edge_recall,
                "edge_precision": self.edge_precision, "edge_f1": self.edge_f1,
                "node_coverage": self.node_coverage, "formula": self.formula}


def _incident(g: Graph):
    out = {n.id: [] for n in g.nodes}
    inc = {n.id: [] for n in g.nodes}
    for e in g.edges:
        if e.source in out and e.target in inc:
            out[e.source].append(e)
            inc[e.target].append(e)
    return out, inc


def pair_scores(src: Graph, tgt: Graph, iterations: int = 6) -> Dict[Tuple[str, str], float]:
    s_out, s_in = _incident(src)
    t_out, t_in = _incident(tgt)
    roles_s = {n.id: n.role for n in src.nodes}
    roles_t = {n.id: n.role for n in tgt.nodes}
    compat = {(a, b): role_compat(roles_s[a], roles_t[b]) for a in roles_s for b in roles_t}
    compat = {k: v for k, v in compat.items() if v > 0}
    score = dict(compat)

    def side(a, b, ea, eb, forward):
        da, db = len(ea[a]), len(eb[b])
        if da == 0 and db == 0:
            return 1.0
        if da == 0 or db == 0:
            return 0.0
        tot = 0.0
        for x in ea[a]:
            xn = x.target if forward else x.source
            best = 0.0
            for y in eb[b]:
                yn = y.target if forward else y.source
                best = max(best, relation_compat(x.relation, y.relation) * score.get((xn, yn), 0.0))
            tot += best
        return tot / max(da, db)

    for _ in range(iterations):
        new = {}
        for (a, b), c in compat.items():
            nb = 0.5 * side(a, b, s_out, t_out, True) + 0.5 * side(a, b, s_in, t_in, False)
            new[(a, b)] = 0.5 * score[(a, b)] + 0.5 * c * (0.25 + 0.75 * nb)
        score = new
    return score


def map_graphs(src: Graph, tgt: Graph, iterations: int = 6, min_score: float = MIN_PAIR_SCORE) -> Mapping:
    scores = pair_scores(src, tgt, iterations)
    ranked = sorted(scores.items(), key=lambda kv: (-round(kv[1], 12), kv[0][0], kv[0][1]))
    used_s, used_t, pairs = set(), set(), []
    for (a, b), sc in ranked:
        if sc < min_score or a in used_s or b in used_t:
            continue
        used_s.add(a)
        used_t.add(b)
        pairs.append((a, b, round(sc, 6)))
    pairs.sort()
    m = Mapping(node_pairs=pairs)
    pm = m.pair_dict()
    m.unmapped_source = sorted(n.id for n in src.nodes if n.id not in pm)
    inv = set(pm.values())
    m.unmapped_target = sorted(n.id for n in tgt.nodes if n.id not in inv)

    used_edges = set()
    weighted = 0.0
    for e in src.edges:
        a, b = pm.get(e.source), pm.get(e.target)
        if a is None or b is None:
            m.lost_edges.append({"source_edge": e.id, "relation": e.relation, "reason": "endpoint unmapped"})
            continue
        exact = [t for t in tgt.edges if t.source == a and t.target == b and t.relation == e.relation and t.id not in used_edges]
        if exact:
            t = exact[0]
            used_edges.add(t.id)
            weighted += 1.0
            m.edge_pairs.append({"source_edge": e.id, "target_edge": t.id, "status": "preserved",
                                 "relation": e.relation, "target_relation": t.relation})
            continue
        other = [t for t in tgt.edges if t.source == a and t.target == b and t.id not in used_edges]
        rev = [t for t in tgt.edges if t.source == b and t.target == a and t.relation == e.relation and t.id not in used_edges]
        cand = other or rev
        if cand:
            # prefer same sign
            cand.sort(key=lambda t: (relation_compat(e.relation, t.relation) == 0, t.id))
            t = cand[0]
            used_edges.add(t.id)
            same = relation_compat(e.relation, t.relation) > 0
            weighted += 0.4 if same else 0.2
            m.edge_pairs.append({"source_edge": e.id, "target_edge": t.id, "status": "modified",
                                 "relation": e.relation, "target_relation": t.relation,
                                 "detail": ("reversed direction" if not other else
                                            ("relation differs, same sign" if same else "relation differs, opposite sign"))})
        else:
            m.lost_edges.append({"source_edge": e.id, "relation": e.relation, "reason": "no counterpart between mapped nodes"})
    m.unmatched_target_edges = sorted(t.id for t in tgt.edges if t.id not in used_edges)
    ns, nt = len(src.edges), len(tgt.edges)
    m.edge_recall = weighted / ns if ns else 0.0
    m.edge_precision = weighted / nt if nt else 0.0
    p, r = m.edge_precision, m.edge_recall
    m.edge_f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    m.node_coverage = len(pairs) / len(src.nodes) if src.nodes else 0.0
    m.mean_pair_score = sum(s for _, _, s in pairs) / len(pairs) if pairs else 0.0
    m.confidence = round(0.3 * m.mean_pair_score + 0.4 * m.edge_recall + 0.3 * m.node_coverage, 6)
    return m
