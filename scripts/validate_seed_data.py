#!/usr/bin/env python3
"""Validate seed knowledge: schema, vocabularies, sources, coverage of the 12 domains."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from knowledge_base import load_systems, load_domains  # noqa: E402

REQUIRED_DOMAINS = {"biology", "physics", "mechanical_engineering", "mathematics", "chemistry", "architecture",
                    "economics", "ecology", "transportation", "energy_systems", "computer_science", "logistics"}
MIN_TOTAL = 100
MIN_MECHANISMS = 24
MIN_PER_DOMAIN = 6
PROVENANCE = {"sourced", "hypothesis"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}
ALLOWED_VERIFICATION = {"unverified_no_network"}  # nothing may claim verified without an actual successful fetch
BANNED_CITATION_MARKERS = ("doi:", "http", "arxiv", "et al., 20")  # we do not embed unverifiable identifiers


def _norm(c: str) -> str:
    return " ".join(c.lower().split())


def check_system_metadata(s, seen: dict) -> list:
    """Provenance and per-source metadata checks. `seen` maps normalised citation prefix to (full text, meta)."""
    problems = []
    if s.provenance_class not in PROVENANCE:
        problems.append(f"{s.id}: provenance_class must be one of {sorted(PROVENANCE)}")
    if s.provenance_class == "sourced" and not s.sources:
        problems.append(f"{s.id}: sourced system has no sources")
    for src in s.sources:
        c = src.get("citation", "")
        if len(c) < 20 or any(m in c.lower() for m in BANNED_CITATION_MARKERS):
            problems.append(f"{s.id}: suspicious citation {c!r}")
        if src.get("confidence") not in CONFIDENCE_LEVELS:
            problems.append(f"{s.id}: source missing confidence: {c[:40]!r}")
        if src.get("verification") not in ALLOWED_VERIFICATION:
            problems.append(f"{s.id}: source verification must be one of {sorted(ALLOWED_VERIFICATION)}: {c[:40]!r}")
        if not src.get("claim_scope"):
            problems.append(f"{s.id}: source missing claim_scope: {c[:40]!r}")
        key = _norm(c)[:40]
        meta = (src.get("confidence"), src.get("kind"))
        prev = seen.get(key)
        if prev is None:
            seen[key] = (_norm(c), meta, s.id)
        elif prev[0] != _norm(c) or prev[1] != meta:
            problems.append(f"{s.id}: citation conflicts with {prev[2]} (same source, different text or metadata): {c[:40]!r}")
    return problems


def coverage(systems) -> dict:
    cov = {"domain": {}, "provenance_class": {}, "source_confidence": {}, "system_confidence": {}, "kind": {}}
    for s in systems:
        for k, v in (("domain", s.domain), ("provenance_class", s.provenance_class),
                     ("system_confidence", s.confidence), ("kind", s.kind)):
            cov[k][v] = cov[k].get(v, 0) + 1
        for src in s.sources:
            v = src.get("confidence", "missing")
            cov["source_confidence"][v] = cov["source_confidence"].get(v, 0) + 1
    return cov


def validate():
    problems = []
    systems = load_systems()
    seen: dict = {}
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
        problems += check_system_metadata(s, seen)
        if any("\u2014" in x for x in [s.name, s.summary]):
            problems.append(f"{s.id}: em dash")
    if len(systems) < MIN_TOTAL:
        problems.append(f"only {len(systems)} systems, need {MIN_TOTAL}")
    n_mech = sum(1 for s in systems if s.kind == "mechanism")
    if n_mech < MIN_MECHANISMS:
        problems.append(f"only {n_mech} mechanisms, need {MIN_MECHANISMS}")
    for d in REQUIRED_DOMAINS:
        if per.get(d, 0) < MIN_PER_DOMAIN:
            problems.append(f"domain {d} has {per.get(d, 0)} systems, need {MIN_PER_DOMAIN}")
    return systems, per, problems


if __name__ == "__main__":
    systems, per, problems = validate()
    print(f"systems: {len(systems)} (mechanisms: {sum(1 for s in systems if s.kind == 'mechanism')})")
    for group, counts in coverage(systems).items():
        print(f"{group}:")
        for k in sorted(counts):
            print(f"  {k}: {counts[k]}")
    print("note: all source verification fields are unverified_no_network (citations recalled, not checked online)")
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("seed data OK")
