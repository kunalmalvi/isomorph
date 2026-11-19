"""Report builder: turns a finished run into a JSON document and Markdown. Stdlib only.

Every statement keeps its provenance. Simulation outcomes are labelled as simulation, not real world evidence.
"""
from __future__ import annotations

from typing import List


def build_report(title: str, run: dict) -> dict:
    """`run` is RunRecord.to_dict(). Missing stages are reported as not completed, never invented."""
    st = {s["name"]: s for s in run["stages"]}
    out = lambda n: (st.get(n) or {}).get("output") or {}
    matches = out("structural_matching").get("matches", [])
    concepts = out("transformation").get("concepts", [])
    hyps = out("validation").get("hypotheses") or out("hypothesis_generation").get("hypotheses", [])
    vals = {v["hypothesis_id"]: v for v in out("validation").get("validations", [])}
    problem = out("perception").get("problem", {})
    return {
        "title": title, "run_id": run["id"], "run_status": run["status"],
        "stage_status": {n: s["status"] for n, s in st.items()},
        "problem": {"title": problem.get("title"), "statement": problem.get("statement"), "goal": problem.get("goal")},
        "query_domain": out("structural_extraction").get("query_domain"),
        "learned_version": out("perception").get("learned_version"),
        "matches": [{"system_name": m["system_name"], "domain": m["domain"], "score": m["score"],
                     "domain_distance": m["domain_distance"], "limitations": m.get("limitations", [])} for m in matches[:10]],
        "concepts": [{"name": c["name"], "analog": c["analog_name"], "status": c["status"], "rationale": c["rationale"],
                      "caveats": c.get("caveats", [])} for c in concepts],
        "hypotheses": [{"id": h["id"], "statement": h["statement"], "prediction": h["prediction"], "falsifier": h["falsifier"],
                        "provenance": h["provenance"], "status": h["status"],
                        "validation": vals.get(h["id"])} for h in hyps],
        "disclaimer": "Matches are heuristic structural analogies. Validation outcomes come from seeded simulation under stated "
                      "assumptions and are not real-world evidence.",
    }


def report_markdown(rep: dict) -> str:
    L: List[str] = [f"# {rep['title']}", "", f"Run `{rep['run_id']}`, status: {rep['run_status']}", ""]
    p = rep["problem"]
    L += ["## Problem", p.get("statement") or "(not available)", ""]
    if p.get("goal"):
        L += [f"Goal: {p['goal']}", ""]
    L += [f"Detected domain: {rep.get('query_domain') or 'unknown'}"]
    if rep.get("learned_version") not in (None, "v0"):
        L += [f"Perception used learned config version {rep['learned_version']} (see the learning panel for its evidence and gate report)."]
    L += ["", "## Stages"]
    L += [f"- {n}: {s}" for n, s in rep["stage_status"].items()]
    L += ["", "## Top matches"]
    L += [f"- {m['system_name']} ({m['domain']}): score {m['score']}, domain distance {m['domain_distance']}" for m in rep["matches"]] or ["- none"]
    L += ["", "## Transformation concepts"]
    for c in rep["concepts"]:
        L.append(f"- **{c['name']}** from {c['analog']} (constraint status: {c['status']}). {c['rationale']}")
    if not rep["concepts"]:
        L.append("- none")
    L += ["", "## Hypotheses"]
    for h in rep["hypotheses"]:
        L += [f"### {h['id']} ({h['status']}, provenance: {h['provenance']})", f"- Statement: {h['statement']}",
              f"- Prediction: {h['prediction']}", f"- Falsifier: {h['falsifier']}"]
        if h.get("validation"):
            L.append(f"- Validation: {h['validation']['outcome']}. {h['validation']['caveats']}")
    if not rep["hypotheses"]:
        L.append("- none")
    L += ["", "## Disclaimer", rep["disclaimer"], ""]
    return "\n".join(L)
