# Core Schemas

Shapes shared by the engine (dataclasses, stdlib) and the API (pydantic models). Status: DESIGN.

```
Provenance = "source" | "computation" | "user" | "ai_hypothesis"

Node        { id: str, label: str, kind: str, role: str | None, attrs: dict, provenance: Provenance }
Edge        { id: str, source: str, target: str, relation: str, weight: float, provenance: Provenance }
Graph       { nodes: [Node], edges: [Edge] }
Constraint  { id: str, description: str, kind: "hard" | "soft", expression: dict | None, provenance: Provenance }
Variable    { name: str, unit: str | None, min: float | None, max: float | None, role: str }
Problem     { id: str, title: str, statement: str, goal: str, graph: Graph, constraints: [Constraint], variables: [Variable] }

Fingerprint { schema_version: int, functional: [float], relational: [float], topological: [float],
              dynamic: [float], constraint: [float], semantic: [float], hash: str }

ScoreWeights{ functional: 25, relationship: 25, topological: 20, dynamic: 15, constraint: 10, semantic: 5 }  # sum 100
Match       { id: str, system_id: str, score: float, components: {name: {score: float, weight: float, explanation: str}},
              domain_distance: float, same_domain: bool }
Mapping     { node_pairs: [(src, tgt, confidence)], edge_pairs: [...], unmapped_source: [str], unmapped_target: [str], confidence: float }
Transformation { steps: [{order: int, action: str, relies_on: [pair], expected_effect: str}], constraint_report: [...], status: "ok" | "blocked" }
Hypothesis  { id: str, statement: str, prediction: str, falsifier: str, provenance: Provenance, status: str }
ExperimentRun { seed: int, config_hash: str, code_version: str, metrics: dict }
Validation  { hypothesis_id: str, outcome: "untested" | "supported" | "refuted" | "inconclusive", caveats: str, method: str }
```

## Rules
- Scores are in [0,1] per component. The total is the weighted sum scaled to 0 to 100.
- Fingerprint vectors are fixed length per schema_version.
- IDs are stable strings in the engine, uuid in the database.
