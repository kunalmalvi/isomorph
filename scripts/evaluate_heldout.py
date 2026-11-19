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

from evaluation.heldout import BANNER, load_heldout, dcg, ndcg_at, first_rank, run  # noqa: E402,F401


if __name__ == "__main__":
    print(BANNER)
    rows, summary = run()
    for r in rows:
        print(f"{r['query']}: strong {','.join(r['strong'])} rank {r['strong_rank']}; any relevant rank {r['relevant_rank']}; "
              f"nDCG@10 {r['ndcg10']:.3f}; lexical-only strong rank {r['lex_strong_rank']}; "
              f"lookalikes above best strong: {r['lookalikes_above_best_strong'] or 'none'}; top3 {', '.join(r['top3'])}")
    print(json.dumps(summary, indent=1))
    print(BANNER)
