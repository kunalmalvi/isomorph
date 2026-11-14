"""Five stage analogy search with per-component scores.

Stage 1 retrieval: whole-fingerprint vector similarity, keep top-K candidates.
Stage 2 functional: role distribution and behaviour overlap, drop candidates under a floor.
Stage 3 structural: typed graph mapping (relationship) and topological features.
Stage 4 behavioural: dynamics tags and constraint signature.
Stage 5 semantic and ranking: lexical TF-IDF similarity (NOT neural), domain distance (reported, not scored),
        threshold, cross-domain filter, stable ordering.

Score = sum(weight_i * component_i) with weights summing to 100 and components in [0,1].
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from ..schemas import ScoreWeights, System, ROLES
from ..structural_model import StructuralModel, build_model
from ..fingerprint import (compute_fingerprint, build_idf, vector_similarity, cosine, jaccard, closeness,
                           triple_patterns, semantic_embedding, Fingerprint)
from ..mapping_engine import map_graphs, Mapping
from ..domain_engine import DomainRegistry

SEMANTIC_NOTE = ("Semantic score is a lexical TF-IDF cosine over hashed words. It measures shared vocabulary, "
                 "not meaning, and is deliberately given a small weight.")


@dataclass
class Match:
    id: str
    system_id: str
    system_name: str
    domain: str
    score: float
    components: Dict[str, dict]
    domain_distance: float
    same_domain: bool
    mapping: Mapping
    differences: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    stages: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": self.id, "system_id": self.system_id, "system_name": self.system_name, "domain": self.domain,
                "score": self.score, "components": self.components, "domain_distance": self.domain_distance,
                "same_domain": self.same_domain, "mapping": self.mapping.to_dict(),
                "differences": self.differences, "limitations": self.limitations, "flags": self.flags,
                "stages": self.stages}


@dataclass
class SearchReport:
    matches: List[Match]
    weights: dict
    threshold: float
    stage_counts: Dict[str, int]
    excluded: List[dict]
    notes: List[str]

    def to_dict(self) -> dict:
        return {"matches": [m.to_dict() for m in self.matches], "weights": self.weights, "threshold": self.threshold,
                "stage_counts": self.stage_counts, "excluded": self.excluded, "notes": self.notes}


def weighted_jaccard(a: Dict[str, float], b: Dict[str, float]) -> float:
    keys = set(a) | set(b)
    num = sum(min(a.get(k, 0), b.get(k, 0)) for k in keys)
    den = sum(max(a.get(k, 0), b.get(k, 0)) for k in keys)
    return num / den if den else 0.0


def _count_cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    keys = sorted(set(a) | set(b))
    return cosine([a.get(k, 0.0) for k in keys], [b.get(k, 0.0) for k in keys])


class AnalogyEngine:
    def __init__(self, systems: Sequence[System], domains: Optional[DomainRegistry] = None,
                 weights: Optional[ScoreWeights] = None, top_k: int = 25, functional_floor: float = 0.12):
        self.weights = weights or ScoreWeights()
        self.weights.validate()
        self.domains = domains or DomainRegistry()
        self.systems = sorted(systems, key=lambda s: s.id)
        self.top_k = top_k
        self.functional_floor = functional_floor
        self.idf = build_idf([s.text() for s in self.systems])
        self.models = {s.id: build_model(s) for s in self.systems}
        self.fps = {s.id: compute_fingerprint(self.models[s.id], self.idf) for s in self.systems}
        self.by_id = {s.id: s for s in self.systems}

    # ------------------------------------------------------------- components
    def functional_score(self, q: StructuralModel, c: StructuralModel):
        role_sim = 0.5 * _count_cosine(q.role_counts, c.role_counts) + 0.5 * weighted_jaccard(q.role_counts, c.role_counts)
        if q.behaviours and c.behaviours:
            beh = jaccard(q.behaviours, c.behaviours)
            s = 0.6 * role_sim + 0.4 * beh
            expl = f"role overlap {role_sim:.2f} (cosine and weighted Jaccard of role counts), behaviour Jaccard {beh:.2f}"
        else:
            s = role_sim
            expl = f"role overlap {role_sim:.2f}; behaviour tags unavailable on one side so roles only"
        shared = sorted(set(q.role_counts) & set(c.role_counts))
        return s, expl + f"; shared roles: {', '.join(shared) or 'none'}"

    def relationship_score(self, q: StructuralModel, c: StructuralModel, mapping: Mapping):
        qp, cp = triple_patterns(q), triple_patterns(c)
        tri_q = {"|".join(k): float(v) for k, v in qp.items()}
        tri_c = {"|".join(k): float(v) for k, v in cp.items()}
        tri = _count_cosine(tri_q, tri_c)
        s = 0.75 * mapping.edge_f1 + 0.25 * tri
        expl = (f"edge F1 {mapping.edge_f1:.2f} under role constrained mapping (recall {mapping.edge_recall:.2f}, "
                f"precision {mapping.edge_precision:.2f}; {len(mapping.preserved)} preserved, {len(mapping.modified)} modified, "
                f"{len(mapping.lost_edges)} lost), role-relation-role pattern cosine {tri:.2f}")
        return s, expl

    def topological_score(self, fq: Fingerprint, fc: Fingerprint, q: StructuralModel, c: StructuralModel):
        diff = sum(abs(x - y) for x, y in zip(fq.topological, fc.topological)) / max(len(fq.topological), 1)
        s = max(0.0, 1.0 - 2.0 * diff)
        mq, mc = q.metrics, c.metrics
        expl = (f"feature distance {diff:.2f}; nodes {mq['node_count']} vs {mc['node_count']}, edges {mq['edge_count']} vs "
                f"{mc['edge_count']}, cycles {mq['cycle_count']} vs {mc['cycle_count']}, depth {mq['depth']} vs {mc['depth']}")
        return s, expl

    def dynamic_score(self, q: StructuralModel, c: StructuralModel):
        if not c.dynamics or (c.dynamics_declared and not c.declared_dynamics):
            return 0.0, "candidate has no dynamics data; scored 0", ["no_dynamics_data"]
        if not q.dynamics:
            return 0.0, "query has no dynamics tags; scored 0", ["query_no_dynamics_data"]
        s = jaccard(q.dynamics, c.dynamics)
        both = sorted(set(q.dynamics) & set(c.dynamics))
        return s, f"dynamics Jaccard {s:.2f}; shared: {', '.join(both) or 'none'}", []

    def constraint_score(self, q: StructuralModel, c: StructuralModel):
        if not q.constraint_tags or not c.constraint_tags:
            return 0.0, "constraint signature unavailable on one side; scored 0", ["no_constraint_data"]
        s = jaccard(q.constraint_tags, c.constraint_tags)
        both = sorted(set(q.constraint_tags) & set(c.constraint_tags))
        return s, f"constraint tag Jaccard {s:.2f}; shared: {', '.join(both) or 'none'}", []

    # ------------------------------------------------------------------ search
    def score_pair(self, q: StructuralModel, fq: Fingerprint, c: StructuralModel, fc: Fingerprint,
                   query_domain: str = "unknown", match_id: Optional[str] = None) -> Match:
        """Full component scoring of one query/candidate pair (no stage filtering)."""
        mapping = map_graphs(q.graph, c.graph)
        func, func_e = self.functional_score(q, c)
        rel, rel_e = self.relationship_score(q, c, mapping)
        topo, topo_e = self.topological_score(fq, fc, q, c)
        dyn, dyn_e, f1 = self.dynamic_score(q, c)
        con, con_e, f2 = self.constraint_score(q, c)
        sem = cosine(fq.semantic, fc.semantic)
        sem_e = f"lexical TF-IDF cosine {sem:.2f}. {SEMANTIC_NOTE}"
        w = self.weights.to_dict()
        raw = {"functional": (func, func_e), "relationship": (rel, rel_e), "topological": (topo, topo_e),
               "dynamic": (dyn, dyn_e), "constraint": (con, con_e), "semantic": (sem, sem_e)}
        comps = {}
        total = 0.0
        for k, (v, e) in raw.items():
            v = max(0.0, min(1.0, v))
            comps[k] = {"score": round(v, 6), "weight": w[k], "contribution": round(v * w[k], 6), "explanation": e}
            total += v * w[k]
        dist = self.domains.distance(query_domain, c.domain)
        m = Match(id=match_id or f"match-{c.id}", system_id=c.id, system_name=c.name, domain=c.domain,
                  score=round(total, 4), components=comps, domain_distance=dist,
                  same_domain=(query_domain == c.domain), mapping=mapping, flags=f1 + f2)
        m.differences = self.differences(q, c, mapping)
        m.limitations = self.limitations(c, mapping, m)
        return m

    @staticmethod
    def differences(q: StructuralModel, c: StructuralModel, mp: Mapping) -> List[str]:
        qn = {n.id: n.label for n in q.graph.nodes}
        cn = {n.id: n.label for n in c.graph.nodes}
        out = []
        for u in mp.unmapped_source:
            out.append(f"Problem element '{qn[u]}' has no counterpart in the analog")
        for u in mp.unmapped_target:
            out.append(f"Analog element '{cn[u]}' has no counterpart in the problem")
        qe = {e.id: e for e in q.graph.edges}
        for l in mp.lost_edges:
            e = qe[l["source_edge"]]
            out.append(f"Problem relationship '{qn[e.source]} {e.relation} {qn[e.target]}' is lost: {l['reason']}")
        for p in mp.modified:
            e = qe[p["source_edge"]]
            out.append(f"Relationship '{qn[e.source]} {e.relation} {qn[e.target]}' maps to '{p['target_relation']}' ({p.get('detail', '')})")
        missing = sorted(set(q.dynamics) - set(c.dynamics))
        if missing:
            out.append("Problem dynamics not present in analog: " + ", ".join(missing))
        extra = sorted(set(c.dynamics) - set(q.dynamics))
        if extra:
            out.append("Analog dynamics not present in problem: " + ", ".join(extra))
        return out

    def limitations(self, c: StructuralModel, mp: Mapping, m: Match) -> List[str]:
        s = self.by_id.get(c.id)
        out = []
        if s is not None:
            out.append(f"Analog entry confidence is {s.confidence}; " + (s.limitations or "no stated limitations"))
        if mp.node_coverage < 0.7:
            out.append(f"Only {mp.node_coverage:.0%} of problem elements are mapped; the analogy is partial")
        if m.same_domain:
            out.append("Same-domain match: not a cross-domain insight")
        out.append("Scores come from heuristic structural features, not a proof of transferability")
        out.append(SEMANTIC_NOTE)
        return out

    def search(self, problem_model: StructuralModel, query_domain: str = "unknown", top_n: int = 10,
               threshold: float = 0.0, cross_domain_only: bool = False,
               exclude_ids: Sequence[str] = ()) -> SearchReport:
        fq = compute_fingerprint(problem_model, self.idf)
        excluded: List[dict] = []
        counts = {"knowledge_base": len(self.systems)}
        pool = [s for s in self.systems if s.id not in set(exclude_ids)]
        if cross_domain_only:
            kept = []
            for s in pool:
                if s.domain == query_domain:
                    excluded.append({"system_id": s.id, "stage": "cross_domain_filter", "reason": "same domain as problem"})
                else:
                    kept.append(s)
            pool = kept
        # stage 1
        sims = sorted(((vector_similarity(fq, self.fps[s.id]), s.id) for s in pool), key=lambda t: (-round(t[0], 12), t[1]))
        stage1 = [sid for _, sid in sims[: self.top_k]]
        for _, sid in sims[self.top_k:]:
            excluded.append({"system_id": sid, "stage": "1_retrieval", "reason": f"outside top {self.top_k} by fingerprint similarity"})
        counts["stage1_retrieval"] = len(stage1)
        # stage 2
        stage2 = []
        for sid in stage1:
            f, _ = self.functional_score(problem_model, self.models[sid])
            if f < self.functional_floor:
                excluded.append({"system_id": sid, "stage": "2_functional", "reason": f"functional score {f:.2f} below floor {self.functional_floor}"})
            else:
                stage2.append(sid)
        counts["stage2_functional"] = len(stage2)
        # stages 3 to 5 (full component scoring)
        scored = [self.score_pair(problem_model, fq, self.models[sid], self.fps[sid], query_domain) for sid in stage2]
        counts["stage3_structural"] = len(scored)
        counts["stage4_behavioural"] = len(scored)
        final = []
        for m in scored:
            if m.score < threshold:
                excluded.append({"system_id": m.system_id, "stage": "5_threshold", "reason": f"score {m.score} below threshold {threshold}"})
            else:
                final.append(m)
        final.sort(key=lambda m: (-round(m.score, 9), m.system_id))
        final = final[:top_n]
        counts["stage5_ranked"] = len(final)
        for i, m in enumerate(final, 1):
            m.id = f"match-{i}-{m.system_id}"
        notes = [SEMANTIC_NOTE, "Domain distance is reported separately and is not part of the score.",
                 f"Threshold {threshold}; weights {self.weights.to_dict()}."]
        return SearchReport(final, self.weights.to_dict(), threshold, counts, excluded, notes)
