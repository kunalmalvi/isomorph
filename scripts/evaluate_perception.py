#!/usr/bin/env python3
"""Evaluate perception role assignment on data/benchmark_problems/perception_heldout.json.

Metrics (all over hand-labelled entities, see the data file):
- detection recall: gold entities matched by a perceived entity (same span text, or same head word).
- role coverage: share of ALL perceived entities that have a role (not None). High coverage is not good by
  itself; it counts guesses too.
- role accuracy: gold entities whose matched perceived entity has the gold role, over ALL gold entities
  (undetected entities count as wrong).
- precision when assigned: correct roles over matched entities that were given a role.

The held-out set was written BEFORE the phase 5 perception changes and must not be edited to fit the code.
The baseline (pre-change) numbers are stored in perception_heldout_baseline.json and printed next to the
current numbers. Pass --write-baseline only on the pre-change code. Stdlib only.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from intelligence.perception import perceive_text  # noqa: E402
from intelligence.schemas import ROLES  # noqa: E402

DATA = os.path.join(ROOT, "data", "benchmark_problems", "perception_heldout.json")
BASELINE = os.path.join(ROOT, "data", "benchmark_problems", "perception_heldout_baseline.json")


def _sing(w):
    w = w.lower()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


def _match(phrase, nodes):
    p = [_sing(w) for w in phrase.lower().split()]
    for n in nodes:
        words = [_sing(w) for w in (n.span or n.label).lower().split()]
        if words == p:
            return n
    for n in nodes:
        words = [_sing(w) for w in (n.span or n.label).lower().split()]
        if words and words[-1] == p[-1]:
            return n
    return None


def evaluate():
    data = json.load(open(DATA))
    gold_total = detected = correct = assigned = assigned_correct = 0
    perceived_total = perceived_with_role = 0
    misses = []
    for prob in data["problems"]:
        for g in prob["entities"]:
            assert g["role"] in ROLES, g
        nodes = [n for n in perceive_text(prob["text"], prob["id"]).problem.graph.nodes]
        perceived_total += len(nodes)
        perceived_with_role += sum(1 for n in nodes if n.role is not None)
        for g in prob["entities"]:
            gold_total += 1
            n = _match(g["phrase"], nodes)
            if n is None:
                misses.append((prob["id"], g["phrase"], g["role"], "not detected"))
                continue
            detected += 1
            if n.role is not None:
                assigned += 1
            if n.role == g["role"]:
                correct += 1
                if n.role is not None:
                    assigned_correct += 1
            else:
                misses.append((prob["id"], g["phrase"], g["role"], f"got {n.role}"))
    return {
        "problems": len(data["problems"]), "gold_entities": gold_total,
        "detection_recall": round(detected / gold_total, 4),
        "role_coverage": round(perceived_with_role / max(perceived_total, 1), 4),
        "role_accuracy": round(correct / gold_total, 4),
        "precision_when_assigned": round(assigned_correct / assigned, 4) if assigned else None,
        "perceived_entities": perceived_total,
    }, misses


def main(argv):
    cur, misses = evaluate()
    if "--write-baseline" in argv:
        json.dump(cur, open(BASELINE, "w"), indent=1)
        print("baseline written")
    base = json.load(open(BASELINE)) if os.path.exists(BASELINE) else None
    print(f"Held-out perception set: {cur['problems']} problems, {cur['gold_entities']} hand-labelled entities")
    print(f"{'metric':26s}{'baseline':>10s}{'current':>10s}")
    for k in ("detection_recall", "role_coverage", "role_accuracy", "precision_when_assigned", "perceived_entities"):
        b = base.get(k) if base else None
        fmt = (lambda v: "n/a" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v)))
        print(f"{k:26s}{fmt(b):>10s}{fmt(cur[k]):>10s}")
    if "-v" in argv:
        for m in misses:
            print("  miss", *m)
    print("NOTE: small hand-labelled set written by the code author; treat as a regression check, not an accuracy estimate.")


if __name__ == "__main__":
    main(sys.argv[1:])
