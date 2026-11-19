"""Perception role evaluation on the frozen data/benchmark_problems/perception_heldout.json.

Shared by scripts/evaluate_perception.py and the learning gate. See the script docstring for metric definitions.
"""
from __future__ import annotations

import json
import os

from knowledge_base.loader import data_dir
from intelligence.perception import perceive_text
from intelligence.schemas import ROLES

DATA = os.path.join(data_dir(), "benchmark_problems", "perception_heldout.json")


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


def evaluate(overlay=None, overlay_version=None):
    data = json.load(open(DATA))
    gold_total = detected = correct = assigned = assigned_correct = 0
    perceived_total = perceived_with_role = 0
    misses = []
    for prob in data["problems"]:
        for g in prob["entities"]:
            assert g["role"] in ROLES, g
        nodes = [n for n in perceive_text(prob["text"], prob["id"], overlay=overlay, overlay_version=overlay_version).problem.graph.nodes]
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
