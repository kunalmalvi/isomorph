#!/usr/bin/env python3
"""Evaluate matching on data/benchmark_problems/benchmarks.json and print retrieval metrics.

Reports: per pair positive score vs negative lookalikes and a rewired control, positive rank among all
candidates (seed + lookalikes + controls), hit@k, MRR, and a lexical-only baseline for comparison.

HONESTY NOTE (tuning and evaluation overlap): the benchmark was written by the same author as the matcher, and
the seed knowledge base was written for the same project. The queries are small hand-authored graphs, the
positives are chosen by a human judgement of structural similarity, and 7 pairs is far too few for statistical
claims. Treat the numbers as regression checks, not as accuracy estimates.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from knowledge_base import load_systems, load_domains, load_benchmarks  # noqa: E402
from knowledge_base.loader import make_rewired_control  # noqa: E402
from intelligence.schemas import Problem, System  # noqa: E402
from intelligence.domain_engine import DomainRegistry  # noqa: E402
from intelligence.analogy_engine import AnalogyEngine  # noqa: E402
from intelligence.structural_model import build_model  # noqa: E402
from intelligence.fingerprint import compute_fingerprint  # noqa: E402


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


if __name__ == "__main__":
    results, summary = run()
    for r in results:
        print(f"{r['query']}: positive {r['positive']} score {r['positive_score']:.1f}; negatives "
              + ", ".join(f"{k}={v:.1f}" for k, v in r["negative_scores"].items())
              + f"; margin {r['margin']:+.1f}; rank {r['positive_rank']} (best acceptable {r['acceptable_best_rank']}, lexical-only rank {r['lexical_only_rank']})")
    print(json.dumps(summary, indent=1))
    print("NOTE: tuning/evaluation overlap and n=7. See the docstring of this script and docs/benchmark-notes.md.")
    sys.exit(0 if summary["positive_beats_all_negatives"] == summary["pairs"] else 1)
