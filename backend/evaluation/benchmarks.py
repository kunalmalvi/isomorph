"""Tuning-set retrieval evaluation shared by scripts/evaluate_benchmarks.py and the learning gate.

Reads the frozen data/benchmark_problems/benchmarks.json for evaluation only. Stdlib only.
"""
from __future__ import annotations

from knowledge_base import load_systems, load_domains, load_benchmarks
from knowledge_base.loader import make_rewired_control
from intelligence.schemas import Problem, System
from intelligence.domain_engine import DomainRegistry
from intelligence.analogy_engine import AnalogyEngine
from intelligence.structural_model import build_model
from intelligence.fingerprint import compute_fingerprint


def run(verbose=True):
    bench = load_benchmarks()
    seed = load_systems()
    domains = DomainRegistry(load_domains())
    results = []
    for pair in bench["pairs"]:
        q = pair["query"]
        problem = Problem.from_dict({k: q[k] for k in ("id", "title", "statement", "goal", "graph", "constraints")})
        qd = q["domain"]
        pos = next(s for s in seed if s.id == pair["positive"])
        negs = [System.from_dict(d) for d in pair["lookalikes"]]
        rewired = make_rewired_control(pos)
        candidates = seed + negs + [rewired]
        eng = AnalogyEngine(candidates, domains)
        qm = build_model(problem, qd)
        fq = compute_fingerprint(qm, eng.idf)
        score = lambda sid: eng.score_pair(qm, fq, eng.models[sid], eng.fps[sid], qd)
        sp = score(pos.id)
        neg_scores = {n.id: score(n.id).score for n in negs}
        neg_scores[rewired.id] = score(rewired.id).score
        best_neg = max(neg_scores.values())
        # rank by full score among all candidates (no pruning) and lexical-only baseline
        full = sorted(((score(s.id).score, s.id) for s in candidates), key=lambda t: (-t[0], t[1]))
        sem = sorted(((score(s.id).components["semantic"]["score"], s.id) for s in candidates), key=lambda t: (-t[0], t[1]))
        rank = lambda lst, sid: 1 + [i for _, i in lst].index(sid)
        acceptable = [a for a in q["acceptable"] if a in {s.id for s in seed}]
        best_acc_rank = min(rank(full, a) for a in acceptable)
        res = {"query": q["id"], "positive": pos.id, "positive_score": sp.score, "negative_scores": neg_scores,
               "margin": round(sp.score - best_neg, 4), "positive_beats_all_negatives": sp.score > best_neg,
               "positive_rank": rank(full, pos.id), "acceptable_best_rank": best_acc_rank,
               "lexical_only_rank": rank(sem, pos.id),
               "components": {k: v["score"] for k, v in sp.components.items()}}
        results.append(res)
    n = len(results)
    summary = {
        "pairs": n,
        "positive_beats_all_negatives": sum(r["positive_beats_all_negatives"] for r in results),
        "mean_margin": round(sum(r["margin"] for r in results) / n, 4),
        "hit_at_1": sum(r["acceptable_best_rank"] <= 1 for r in results) / n,
        "hit_at_3": sum(r["acceptable_best_rank"] <= 3 for r in results) / n,
        "hit_at_5": sum(r["acceptable_best_rank"] <= 5 for r in results) / n,
        "hit_at_10": sum(r["acceptable_best_rank"] <= 10 for r in results) / n,
        "mrr_primary": round(sum(1.0 / r["positive_rank"] for r in results) / n, 4),
        "mrr_lexical_only_baseline": round(sum(1.0 / r["lexical_only_rank"] for r in results) / n, 4),
        "candidates_per_query": len(seed) + 2 + 1,
    }
    return results, summary
