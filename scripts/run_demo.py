#!/usr/bin/env python3
"""Run the full ISOMORPH pipeline on the roller/metal strip demo, offline, and write the sample report.

Usage: python3 scripts/run_demo.py [--reduction 20] [--material copper|silver] [--no-write]
Outputs: docs/sample-discovery-report.md and data/demo/sample_investigation.json (deterministic, no timestamps).
The roller scenario is a DEMO. The engine itself is domain independent.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from knowledge_base import load_systems, load_domains  # noqa: E402
from intelligence.domain_engine import DomainRegistry  # noqa: E402
from intelligence.pipeline import investigate  # noqa: E402
from intelligence.schemas import Constraint, Variable, Provenance  # noqa: E402
from intelligence.learning_engine import MemoryStore  # noqa: E402
from experiments import run_experiment  # noqa: E402
from experiments.runners import MATERIALS  # noqa: E402

SEEDS = tuple(range(20))


def load_problem_spec():
    with open(os.path.join(ROOT, "data", "demo", "roller_problem.json")) as f:
        return json.load(f)


def model_values(params, material, reduction_fraction):
    """Deterministic roll model outputs used by the constraint checks (computation provenance)."""
    r = run_experiment("strip_rolling_model", {"reduction": reduction_fraction, "material": material,
                                               "thickness_mm": params["thickness_mm"], "width_mm": params["width_mm"],
                                               "roll_radius_mm": params["roll_radius_mm"], "friction": params["friction"]}).metrics
    gauge = lambda mode: [run_experiment("strip_rolling_gauge", dict(_gauge_params(params, material, reduction_fraction), mode=mode), s).metrics
                          for s in SEEDS]
    base, fb = gauge("open"), gauge("feedback")
    mean = lambda rs, k: sum(x[k] for x in rs) / len(rs)
    passes = run_experiment("strip_rolling_passes", {"reduction": reduction_fraction, "material": material, "passes": 2,
                                                     "thickness_mm": params["thickness_mm"], "width_mm": params["width_mm"],
                                                     "roll_radius_mm": params["roll_radius_mm"], "friction": params["friction"]}).metrics
    return {"single_pass": r, "baseline_rms_dev_mm": mean(base, "rms_dev_mm"), "feedback_rms_dev_mm": mean(fb, "rms_dev_mm"),
            "two_pass": passes}


def _gauge_params(params, material, reduction_fraction):
    return {"reduction": reduction_fraction, "material": material, "thickness_mm": params["thickness_mm"],
            "width_mm": params["width_mm"], "roll_radius_mm": params["roll_radius_mm"], "friction": params["friction"],
            "mill_modulus_kn_per_mm": params["mill_modulus_kn_per_mm"], "tolerance_mm": params["tolerance_mm"]}


def run_demo(reduction_percent=None, material="copper", memory=None):
    spec = load_problem_spec()
    params = dict(spec["parameters"])
    if reduction_percent is not None:
        params["reduction_percent"] = float(reduction_percent)
    red = params["reduction_percent"] / 100.0
    mv = model_values(params, material, red)
    sp = mv["single_pass"]
    values = {"thickness_mm": params["thickness_mm"], "reduction_fraction": red, "roll_radius_mm": params["roll_radius_mm"],
              "friction": params["friction"], "roll_force_kn": sp["roll_force_kn"], "rms_dev_mm": mv["baseline_rms_dev_mm"]}

    def hook(problem):
        by_name = {v.name: v for v in problem.variables}
        for name, unit, val in (("width", "mm", params["width_mm"]), ("thickness", "mm", params["thickness_mm"]),
                                ("reduction", "%", params["reduction_percent"])):
            by_name[name] = Variable(name, unit, role="parameter", value=val)
        for name, unit, val in (("thickness_mm", "mm", values["thickness_mm"]), ("reduction_fraction", None, red),
                                ("roll_radius_mm", "mm", params["roll_radius_mm"]), ("friction", None, params["friction"]),
                                ("roll_force_kn", "kN", values["roll_force_kn"]), ("rms_dev_mm", "mm", values["rms_dev_mm"])):
            by_name[name] = Variable(name, unit, role="model_output" if name in ("roll_force_kn", "rms_dev_mm") else "parameter", value=val)
        problem.variables = list(by_name.values())
        problem.constraints = [
            Constraint("c_force", f"Roll force must not exceed {params['roll_force_limit_kn']} kN", "hard",
                       {"var": "roll_force_kn", "op": "<=", "value": params["roll_force_limit_kn"]}, Provenance.USER, ["capacity_limit", "hard_limit"]),
            Constraint("c_bite", "Draft per pass must satisfy the bite condition", "hard",
                       {"validator": "bite_condition"}, Provenance.USER, ["hard_limit"]),
            Constraint("c_tol", f"Thickness variation (RMS) must not exceed {params['tolerance_mm']} mm", "soft",
                       {"var": "rms_dev_mm", "op": "<=", "value": params["tolerance_mm"]}, Provenance.USER, ["safety_bound"]),
        ]
        return problem

    overrides = {"close_feedback_loop": {"rms_dev_mm": mv["feedback_rms_dev_mm"]},
                 "distribute_load": {"roll_force_kn": mv["two_pass"]["peak_roll_force_kn"], "reduction_fraction": 1 - (1 - red) ** 0.5}}
    ctx = {"material": material, "friction": params["friction"], "roll_radius_mm": params["roll_radius_mm"],
           "mill_modulus_kn_per_mm": params["mill_modulus_kn_per_mm"], "tolerance_mm": params["tolerance_mm"]}
    domains = DomainRegistry(load_domains())
    result = investigate(spec["statement"], load_systems(), domains, title=spec["title"], query_domain="mechanical_engineering",
                         cross_domain_only=True, problem_hook=hook, concept_overrides=overrides,
                         experiment_context=ctx, memory=memory, seeds=SEEDS)
    result["params"], result["material"], result["model_values"], result["spec"] = params, material, mv, spec
    return result


def material_table(params):
    rows = []
    for mat in ("copper", "silver"):
        for pct in (10, 20, 30, 40, 50):
            m = run_experiment("strip_rolling_model", {"reduction": pct / 100, "material": mat, "thickness_mm": params["thickness_mm"],
                                                       "width_mm": params["width_mm"], "roll_radius_mm": params["roll_radius_mm"],
                                                       "friction": params["friction"]}).metrics
            p2 = run_experiment("strip_rolling_passes", {"reduction": pct / 100, "material": mat, "passes": 2, "thickness_mm": params["thickness_mm"],
                                                         "width_mm": params["width_mm"], "roll_radius_mm": params["roll_radius_mm"],
                                                         "friction": params["friction"]}).metrics
            rows.append({"material": mat, "reduction_percent": pct, "force_1_pass_kn": m["roll_force_kn"], "bite_1_pass": m["bite_ok"],
                         "peak_force_2_pass_kn": p2["peak_roll_force_kn"], "bite_2_pass": p2["all_passes_bite_ok"],
                         "within_limit_1": m["roll_force_kn"] <= params["roll_force_limit_kn"] and m["bite_ok"],
                         "within_limit_2": p2["peak_roll_force_kn"] <= params["roll_force_limit_kn"] and p2["all_passes_bite_ok"]})
    return rows


def to_json(r, table):
    return {"demo_only_scenario": True, "material": r["material"], "parameters": r["params"], "query_domain": r["query_domain"],
            "perception": r["perception"].to_dict() if r["perception"] else None, "problem": r["problem"].to_dict(),
            "structural_metrics": r["model"].metrics, "search": r["search"].to_dict(),
            "concepts": [c.to_dict() for c in r["concepts"]], "hypotheses": [h.to_dict() for h in r["hypotheses"]],
            "validations": [v.to_dict() for v in r["validations"]], "model_values": r["model_values"],
            "material_reduction_table": table,
            "material_assumptions": {k: MATERIALS[k] for k in MATERIALS}}


def fmt(x, nd=3):
    return f"{x:.{nd}f}" if isinstance(x, float) else str(x)


def render_report(r, table):
    p, params, search = r["problem"], r["params"], r["search"]
    L = []
    w = L.append
    w("# ISOMORPH sample discovery report")
    w("")
    w("Generated by `scripts/run_demo.py`. Deterministic: same inputs give the same report. No network, no language model.")
    w("The roller and metal strip scenario is a **demo**. The engine takes any problem; `backend/tests/intelligence/test_generality.py` runs unrelated problems through it.")
    w("")
    w("## Honest status")
    w("- Matching is heuristic structural scoring, not a proof of transferability. Scores come from the component breakdown below.")
    w("- Semantic similarity is a lexical hashed TF-IDF cosine, not a neural embedding.")
    w("- Experiments are simplified simulations with stated assumptions. A 'supported' outcome means supported in simulation only.")
    w(f"- Material data: copper uses a commonly tabulated power-law fit (confidence medium). Silver uses an **assumed placeholder** (confidence low). Replace both with measured flow curves before relying on forces.")
    w("")
    w("## 1. Problem and perception")
    w(f"Statement: {p.statement}")
    w("")
    w(f"Target reduction: {params['reduction_percent']:g} percent on {params['thickness_mm']:g} mm thickness, {params['width_mm']:g} mm width. Material for this run: {r['material']}.")
    pr = r["perception"]
    w("")
    w("Entities extracted (role inferred from keyword lexicon):")
    for n in p.graph.nodes:
        w(f"- {n.label} ({n.role})")
    w("")
    w("Relationships extracted:")
    lab = {n.id: n.label for n in p.graph.nodes}
    for e in p.graph.edges:
        flag = " [assumed]" if "assumed_relation" in e.flags else ""
        w(f"- {lab[e.source]} --{e.relation}--> {lab[e.target]}{flag}")
    w("")
    w("Facts (stated by the user): " + "; ".join(f["statement"] for f in pr.facts if "mentioned" not in f["statement"]))
    w("")
    w("Assumptions made by the extractor: " + ("; ".join(a["statement"] for a in pr.assumptions) or "none"))
    w("")
    w("Unknowns: " + ("; ".join(pr.unknowns) or "none"))
    w("")
    w("Clarification questions: " + ("; ".join(pr.clarification_questions) or "none"))
    w("")
    w("## 2. Structural model")
    m = r["model"].metrics
    w(f"Nodes {m['node_count']}, edges {m['edge_count']}, cycles {m['cycle_count']} (negative loops {m['negative_loops']}, positive loops {m['positive_loops']}), depth {m['depth']}.")
    w(f"Dynamics tags: {', '.join(r['model'].dynamics) or 'none'}. Constraint tags: {', '.join(r['model'].constraint_tags) or 'none'}.")
    w("")
    w("## 3. Cross-domain matches (same-domain entries excluded)")
    w(f"Weights: {search.weights}. Stage counts: {search.stage_counts}.")
    w("")
    w("| Rank | System | Domain | Score | Functional | Relationship | Topological | Dynamic | Constraint | Semantic | Domain distance |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for i, mt in enumerate(search.matches[:10], 1):
        c = mt.components
        w(f"| {i} | {mt.system_name} | {mt.domain} | {mt.score:.1f} | " + " | ".join(f"{c[k]['score']:.2f}" for k in ("functional", "relationship", "topological", "dynamic", "constraint", "semantic")) + f" | {mt.domain_distance:.1f} |")
    w("")
    top = search.matches[0].score if search.matches else 0.0
    w(f"Reading the table: the best score is {top:.1f} out of 100. " + (
        "That is a weak match overall. The problem as stated is an open chain with no feedback loop, so relationship scores are low and "
        "ranking is driven mostly by role, constraint and topology overlap. Treat the analogs as idea prompts, not as validated models."
        if top < 50 else "Scores above 50 indicate a substantial shared structure, but still not a proof of transferability."))
    w("")
    for mt in search.matches[:3]:
        w(f"### Match detail: {mt.system_name} ({mt.domain}), score {mt.score:.1f}")
        for k, v in mt.components.items():
            w(f"- {k} {v['score']:.2f} x weight {v['weight']:g}: {v['explanation']}")
        w(f"- Mapping confidence {mt.mapping.confidence:.2f} ({mt.mapping.formula})")
        w("- Mapped pairs (problem -> analog, confidence): " + "; ".join(f"{s} -> {t} ({c:.2f})" for s, t, c in mt.mapping.node_pairs))
        w("- Preserved relationships: " + str(len(mt.mapping.preserved)) + ", modified: " + str(len(mt.mapping.modified)) + ", lost: " + str(len(mt.mapping.lost_edges)))
        w("- Differences: " + ("; ".join(mt.differences[:8]) or "none"))
        w("- Limitations: " + "; ".join(mt.limitations[:3]))
        w("")
    w("## 4. Transformation concepts (distinct)")
    for c in r["concepts"]:
        w(f"### {c.name} (from {c.analog_name}, analog score {c.analog_score:.1f})")
        w(f"- Concept type: `{c.concept_type}`. Constraint status: **{c.status}**.")
        w(f"- Why: {c.rationale}.")
        for s in c.steps:
            w(f"  {s['order']}. {s['action']}")
        w(f"- Relies on mapping pairs (problem, analog, confidence): {c.relies_on}")
        w(f"- Expected effect: {c.expected_effect}.")
        for res in c.constraint_report["results"]:
            w(f"- Constraint {res['constraint_id']} ({res['kind']}): {res['outcome']} ({res['detail']})")
        w("")
    w("## 5. Hypotheses and validation")
    for h, v in zip(r["hypotheses"], r["validations"]):
        w(f"### {h.id} ({h.category})")
        w(f"- Statement: {h.statement}")
        w(f"- Prediction: {h.prediction}")
        w(f"- Falsifier: {h.falsifier}")
        w(f"- Outcome: **{v.outcome}** by {v.method}")
        ev = v.evidence
        if "baseline_mean" in ev:
            w(f"- Baseline mean {ev['metric']}: {ev['baseline_mean']:.4g}; proposed mean: {ev['proposed_mean']:.4g}; relative improvement {ev['mean_relative_improvement']:.1%} (95% CI half-width {ev['ci95_half_width']:.1%}); proposed wins in {ev['win_rate']:.0%} of {ev['n']} seeded runs. Config hashes {ev['config_hashes']}, code version {ev['code_version']}.")
            if ev["other_metric_changes"]:
                w("- Other metrics that moved more than 5 percent: " + "; ".join(f"{t['metric']} {t['baseline_mean']:.4g} -> {t['proposed_mean']:.4g}" for t in ev["other_metric_changes"]))
        w(f"- Caveats: {v.caveats}")
        w("")
    w("## 6. Rolling model sensitivity (single pass versus two passes)")
    w(f"Force limit {params['roll_force_limit_kn']:g} kN (assumed). 'Bite' is the friction bite condition. Silver rows use placeholder material data.")
    w("")
    w("| Material | Reduction % | 1 pass force kN | 1 pass bite | 1 pass ok | 2 pass peak force kN | 2 pass ok |")
    w("|---|---|---|---|---|---|---|")
    for t in table:
        w(f"| {t['material']} | {t['reduction_percent']} | {t['force_1_pass_kn']:.1f} | {t['bite_1_pass']} | {t['within_limit_1']} | {t['peak_force_2_pass_kn']:.1f} | {t['within_limit_2']} |")
    w("")
    w("## 7. Limits of this report")
    w("- The rolling model is a simplified plane strain pass model without roll flattening, tension or temperature rise.")
    w("- Disturbance statistics, mill stiffness, friction and the force limit are stated assumptions in `data/demo/roller_problem.json`.")
    w("- Analog entries are qualitative abstractions of real systems. Cited references support the underlying system description, not the exact graph.")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reduction", type=float, default=None, help="reduction in percent (default from roller_problem.json)")
    ap.add_argument("--material", default="copper", choices=["copper", "silver"])
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    mem = MemoryStore()
    r = run_demo(a.reduction, a.material, mem)
    table = material_table(r["params"])
    print(f"Query domain: {r['query_domain']}; material {r['material']}; reduction {r['params']['reduction_percent']:g}%")
    print("Top cross-domain matches:")
    for mt in r["search"].matches[:5]:
        print(f"  {mt.score:5.1f}  {mt.system_name} ({mt.domain})")
    print(f"Distinct transformation concepts: {len(r['concepts'])}")
    for c in r["concepts"]:
        print(f"  - {c.name} [{c.concept_type}] from {c.analog_name}: constraints {c.status}")
    print("Hypotheses:")
    for h, v in zip(r["hypotheses"], r["validations"]):
        ev = v.evidence
        extra = (f" baseline {ev['baseline_mean']:.4g} vs proposed {ev['proposed_mean']:.4g} ({ev['metric']})" if "baseline_mean" in ev else "")
        print(f"  - {h.id}: {v.outcome}{extra}")
    if not a.no_write:
        report = render_report(r, table)
        with open(os.path.join(ROOT, "docs", "sample-discovery-report.md"), "w") as f:
            f.write(report)
        with open(os.path.join(ROOT, "data", "demo", "sample_investigation.json"), "w") as f:
            json.dump(to_json(r, table), f, indent=1, sort_keys=True, default=str)
            f.write("\n")
        print("wrote docs/sample-discovery-report.md and data/demo/sample_investigation.json")


if __name__ == "__main__":
    main()
