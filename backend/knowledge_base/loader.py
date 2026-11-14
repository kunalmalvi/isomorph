"""Loads seed knowledge (systems, mechanisms, domains, benchmarks) from data/ (stdlib only)."""
from __future__ import annotations

import glob
import json
import os
from typing import Dict, List, Optional

from intelligence.schemas import System

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")


def data_dir(path: Optional[str] = None) -> str:
    return os.path.abspath(path or os.environ.get("ISOMORPH_DATA_DIR") or DEFAULT_DATA_DIR)


def load_systems(path: Optional[str] = None, include_mechanisms: bool = True) -> List[System]:
    base = data_dir(path)
    folders = ["seed_knowledge"] + (["mechanisms"] if include_mechanisms else [])
    out: List[System] = []
    for folder in folders:
        for fp in sorted(glob.glob(os.path.join(base, folder, "*.json"))):
            with open(fp) as f:
                doc = json.load(f)
            out.extend(System.from_dict(s) for s in doc["systems"])
    out.sort(key=lambda s: s.id)
    return out


def load_domains(path: Optional[str] = None) -> dict:
    with open(os.path.join(data_dir(path), "domains", "domains.json")) as f:
        return json.load(f)


def load_benchmarks(path: Optional[str] = None) -> dict:
    with open(os.path.join(data_dir(path), "benchmark_problems", "benchmarks.json")) as f:
        return json.load(f)


def systems_by_id(systems: List[System]) -> Dict[str, System]:
    return {s.id: s for s in systems}


def make_rewired_control(system: System, new_id: Optional[str] = None) -> System:
    """Adversarial control: same nodes and roles, edge targets rotated by one position.

    Keeps the role distribution, edge count and relation multiset, but destroys the wiring. A structure-aware
    matcher must score it below the original.
    """
    import copy
    s = copy.deepcopy(system)
    s.id = new_id or f"rewired_{system.id}"
    s.name = f"{system.name} (rewired control)"
    edges = s.graph.edges
    targets = [e.target for e in edges]
    rotated = targets[1:] + targets[:1]
    for e, t in zip(edges, rotated):
        e.target = t
    s.sources = [{"citation": "synthetic benchmark control, not a real system", "kind": "synthetic", "note": ""}]
    return s
