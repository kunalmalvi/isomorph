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

from evaluation.benchmarks import run  # noqa: E402,F401


if __name__ == "__main__":
    results, summary = run()
    for r in results:
        print(f"{r['query']}: positive {r['positive']} score {r['positive_score']:.1f}; negatives "
              + ", ".join(f"{k}={v:.1f}" for k, v in r["negative_scores"].items())
              + f"; margin {r['margin']:+.1f}; rank {r['positive_rank']} (best acceptable {r['acceptable_best_rank']}, lexical-only rank {r['lexical_only_rank']})")
    print(json.dumps(summary, indent=1))
    print("NOTE: tuning/evaluation overlap and n=7. See the docstring of this script and docs/benchmark-notes.md.")
    sys.exit(0 if summary["positive_beats_all_negatives"] == summary["pairs"] else 1)
