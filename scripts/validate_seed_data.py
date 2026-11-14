#!/usr/bin/env python3
"""Validate seed knowledge: schema, vocabularies, sources, coverage of the 12 domains."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from knowledge_base import load_systems, load_domains  # noqa: E402

REQUIRED_DOMAINS = {"biology", "physics", "mechanical_engineering", "mathematics", "chemistry", "architecture",
                    "economics", "ecology", "transportation", "energy_systems", "computer_science", "logistics"}
MIN_TOTAL = 50
MIN_PER_DOMAIN = 3
BANNED_CITATION_MARKERS = ("doi:", "http", "arxiv", "et al., 20")  # we do not embed unverifiable identifiers


def validate():
    problems = []
    systems = load_systems()
    domains = {d["id"] for d in load_domains()["domains"]}
    if domains != REQUIRED_DOMAINS:
        problems.append(f"domain list mismatch: {sorted(domains ^ REQUIRED_DOMAINS)}")
    ids = [s.id for s in systems]
    if len(ids) != len(set(ids)):
        problems.append("duplicate system ids")
    per: dict = {}
    for s in systems:
        problems += s.validate()
        if s.domain not in domains:
            problems.append(f"{s.id}: unknown domain {s.domain}")
        per[s.domain] = per.get(s.domain, 0) + 1
        for src in s.sources:
            c = src.get("citation", "")
            if len(c) < 20 or any(m in c.lower() for m in BANNED_CITATION_MARKERS):
                problems.append(f"{s.id}: suspicious citation {c!r}")
        if any("\u2014" in x for x in [s.name, s.summary]):
            problems.append(f"{s.id}: em dash")
    if len(systems) < MIN_TOTAL:
        problems.append(f"only {len(systems)} systems, need {MIN_TOTAL}")
    for d in REQUIRED_DOMAINS:
        if per.get(d, 0) < MIN_PER_DOMAIN:
            problems.append(f"domain {d} has {per.get(d, 0)} systems, need {MIN_PER_DOMAIN}")
    return systems, per, problems


if __name__ == "__main__":
    systems, per, problems = validate()
    print(f"systems: {len(systems)} (mechanisms: {sum(1 for s in systems if s.kind == 'mechanism')})")
    for d in sorted(per):
        print(f"  {d}: {per[d]}")
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("seed data OK")
