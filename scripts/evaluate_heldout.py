#!/usr/bin/env python3
"""Run the matcher, unchanged, over the held-out set data/benchmark_problems/heldout_labels.json.

Reports hit@k (strong analog in top k), MRR of the first strong analog, nDCG@10 with graded labels (2/1/0),
how many labelled lookalikes outrank the best strong analog, and a lexical-only baseline (semantic component
alone). Candidates are all systems in the knowledge base. Unlabelled candidates count as grade 0.

HONESTY: labels are author_labelled and have NOT been independently reviewed. The author of the labels also wrote
the matcher, so the held-out set is only less overlapping with the tuning set, not independent.
"""
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from knowledge_base import load_systems, load_domains  # noqa: E402
from intelligence.schemas import Problem  # noqa: E402
from intelligence.domain_engine import DomainRegistry  # noqa: E402
from intelligence.analogy_engine import AnalogyEngine  # noqa: E402
from intelligence.structural_model import build_model  # noqa: E402
from intelligence.fingerprint import compute_fingerprint  # noqa: E402

BANNER = ("BANNER: held-out labels are AUTHOR-LABELLED and NOT INDEPENDENTLY REVIEWED. The label author also wrote the "
          "matcher, so this set is less overlapping with the tuning set but is not independent. Treat results as indicative only.")


def load_heldout(path=None):
    path = path or os.path.join(ROOT, "data", "benchmark_problems", "heldout_labels.json")
    with open(path) as f:
        return json.load(f)


def dcg(gains):
    return sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at(ranked_ids, grades, k=10):
    gains = [grades.get(i, 0) for i in ranked_ids[:k]]
    ideal = sorted(grades.values(), reverse=True)[:k]
    d = dcg(ideal)
    return dcg(gains) / d if d > 0 else 0.0


def first_rank(ranked_ids, wanted):
    for i, sid in enumerate(ranked_ids, 1):
        if sid in wanted:
            return i
    return len(ranked_ids) + 1


def run(doc=None):
    doc = doc or load_heldout()
    seed = load_systems()
    domains = DomainRegistry(load_domains())
    eng = AnalogyEngine(seed, domains)
    rows = []
    for item in doc["items"]:
        q = item["query"]
        problem = Problem.from_dict({k: q[k] for k in ("id", "title", "statement", "goal", "graph", "constraints")})
        qm = build_model(problem, q["domain"])
        fq = compute_fingerprint(qm, eng.idf)
        scores = {}
        sem = {}
        for s in seed:
            r = eng.score_pair(qm, fq, eng.models[s.id], eng.fps[s.id], q["domain"])
            scores[s.id] = r.score
            sem[s.id] = r.components["semantic"]["score"]
        full = [i for _, i in sorted(((-v, k) for k, v in scores.items()))]
        lex = [i for _, i in sorted(((-v, k) for k, v in sem.items()))]
        grades = {l["system_id"]: l["grade"] for l in item["labels"]}
        strong = {i for i, g in grades.items() if g == 2}
        relevant = {i for i, g in grades.items() if g >= 1}
        looks = [l["system_id"] for l in item["labels"] if l["lookalike"]]
        best_strong = min(first_rank(full, strong), len(full) + 1)
        beat = [i for i in looks if full.index(i) + 1 < best_strong]
        rows.append({
            "query": q["id"], "strong_rank": best_strong, "relevant_rank": first_rank(full, relevant),
            "ndcg10": round(ndcg_at(full, grades), 4), "lex_strong_rank": first_rank(lex, strong),
            "lex_ndcg10": round(ndcg_at(lex, grades), 4), "lookalikes_above_best_strong": beat,
            "top3": full[:3], "strong": sorted(strong)})
    n = len(rows)
    summary = {
        "queries": n, "candidates_per_query": len(seed),
        "hit_at_1_strong": sum(r["strong_rank"] <= 1 for r in rows) / n,
        "hit_at_3_strong": sum(r["strong_rank"] <= 3 for r in rows) / n,
        "hit_at_5_strong": sum(r["strong_rank"] <= 5 for r in rows) / n,
        "hit_at_10_strong": sum(r["strong_rank"] <= 10 for r in rows) / n,
        "hit_at_3_any_relevant": sum(r["relevant_rank"] <= 3 for r in rows) / n,
        "mrr_strong": round(sum(1.0 / r["strong_rank"] for r in rows) / n, 4),
        "ndcg_at_10": round(sum(r["ndcg10"] for r in rows) / n, 4),
        "lookalike_beats_best_strong": sum(len(r["lookalikes_above_best_strong"]) for r in rows),
        "queries_with_lookalike_beating_strong": sum(bool(r["lookalikes_above_best_strong"]) for r in rows),
        "lexical_only": {
            "hit_at_1_strong": sum(r["lex_strong_rank"] <= 1 for r in rows) / n,
            "hit_at_3_strong": sum(r["lex_strong_rank"] <= 3 for r in rows) / n,
            "mrr_strong": round(sum(1.0 / r["lex_strong_rank"] for r in rows) / n, 4),
            "ndcg_at_10": round(sum(r["lex_ndcg10"] for r in rows) / n, 4)},
        "label_status": doc.get("label_status"), "independent_review": doc.get("independent_review")}
    return rows, summary


if __name__ == "__main__":
    print(BANNER)
    rows, summary = run()
    for r in rows:
        print(f"{r['query']}: strong {','.join(r['strong'])} rank {r['strong_rank']}; any relevant rank {r['relevant_rank']}; "
              f"nDCG@10 {r['ndcg10']:.3f}; lexical-only strong rank {r['lex_strong_rank']}; "
              f"lookalikes above best strong: {r['lookalikes_above_best_strong'] or 'none'}; top3 {', '.join(r['top3'])}")
    print(json.dumps(summary, indent=1))
    print(BANNER)
