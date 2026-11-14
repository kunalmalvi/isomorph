# Product Vision
ISOMORPH helps people solve hard problems by finding structurally similar solved problems in other domains, mapping them, and turning them into testable hypotheses.

## Principles
- Structure over surface: match on function, relationships, topology, dynamics and constraints, not keywords.
- Honest uncertainty: show confidence, unmapped elements and caveats. An analogy is a suggestion, not proof.
- No fake intelligence: if the engine cannot produce a result, say so. Do not pad with plausible filler.
- Provenance everywhere: each claim is tagged source, computation, user or ai_hypothesis.
- No dead UI: every control must work against a real backend action.

## Non-goals
- Claiming real-world validation from simulation.
- Replacing expert judgment.

## Concrete consequences in the product (phase 3)
- Match output shows the six component scores and the weights (25, 25, 20, 15, 10, 5). Domain distance is shown beside the score and never added to it.
- A mapping lists unmapped elements. When no valid mapping exists the engine says so.
- Reports carry a provenance disclaimer and mark stages that have not run.
- Simulations are models. Validation labels them with a caveat.
- Perception is keyword based with synonyms. It does not understand arbitrary prose, and the UI and docs must not imply it does.
- PDF and image uploads are stored only. The response says they were not interpreted.
