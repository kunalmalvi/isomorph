# Labelling guide for structural analog judgements

Status: written by the same author who wrote the matcher. No independent reviewer has used this guide yet.

This guide defines how a person decides whether a candidate system is a structural analog of a query problem. It is
written so that a second person can apply it without seeing any matcher output.

## What a reviewer must NOT use

- Matcher scores, ranks, component scores, or any output of `scripts/evaluate_benchmarks.py` or
  `scripts/evaluate_heldout.py`.
- The order in which a system would be suggested by the tool.
- The domain label as evidence. Two systems from the same domain are not analogs because of the domain, and two
  systems from different domains are not analogs because they differ in domain.

Use only the query graph (nodes, roles, edges, constraints, statement) and the candidate graph (nodes, roles, edges,
behaviours, dynamics, constraints) as written in the data files.

## Definition of a structural analog

A candidate is a structural analog of the query when the following four checks hold, in this order.

1. **Role mapping.** You can map query nodes to candidate nodes so that mapped nodes play the same functional role
   (for example sensor to sensor, buffer to buffer, regulator to regulator). Nodes may be merged or left unmapped, but
   every node on the main loop or flow path of the query must have an image.
2. **Edge-relation correspondence.** Each mapped query edge corresponds to a candidate edge between the images with a
   compatible relation (flow to flow, sensed-by to sensed-by, inhibition to inhibition, activation to activation).
   Direction matters. Reversing a sensing or inhibition edge changes the meaning.
3. **Shared dynamics.** The mapped structure produces the same kind of behaviour: regulation to a set point,
   queue growth with spillback, damped oscillation, saturating growth, runaway reinforcement, and so on.
4. **Constraint correspondence.** The constraints of the query (capacity limit, conservation, non-negativity,
   safety limit) have a counterpart on the mapped parts of the candidate, or the candidate's constraints are at least
   not contradicted by the query.

## Grades

| Grade | Meaning | Rule of thumb |
|---|---|---|
| 2 | Strong analog | All four checks hold. At most one minor node is merged or unmapped and no edge on the main loop or path is missing. |
| 1 | Partial analog | A useful sub-structure maps (for example the feedback loop but not the storage, or the chain but not the loop), or checks 1 to 3 hold with a missing or reversed secondary edge. |
| 0 | Not an analog | Mapping fails on the main loop or path, or the shared behaviour differs. |

### Lookalike rule: same words, wrong wiring = 0

A **lookalike** is a candidate that looks similar to the query on the surface but is wired differently. Typical
causes: similar node names or similar role types, a sensor that feeds a display instead of a controller, parts in
series where the query has parts in parallel, a feedback edge that is missing or points the wrong way, a loop that
reinforces where the query's loop opposes. A lookalike receives grade 0 unless a genuine sub-structure maps, in which
case it receives grade 1 and is not marked as a lookalike. Mark `lookalike: true` only for grade 0 entries chosen for
surface similarity, and give the reason in `lookalike_reason`.

## Worked examples (from the 7 tuning pairs)

These come from `data/benchmark_problems/benchmarks.json` (split `tuning`).

- **Data center cooling to human thermoregulation: grade 2.** Servers map to heat production, room temperature to
  core temperature, temperature sensors to thermoreceptors, cooling controller to hypothalamus, fans to sweat glands,
  outside air to environment. Sensor to controller to actuator, and actuator opposing the controlled quantity, all
  correspond. Both regulate to a set point and have a capacity limit on the actuator.
- **Data center with timer fans: grade 0 (lookalike).** Same nodes and words, but the sensor feeds a display and the
  controller is not driven by the sensor. There is no loop, so check 3 fails.
- **Router bottleneck to highway bottleneck: grade 2.** Senders to demand, upstream link to upstream road,
  bottleneck link to bottleneck, packet buffer to queue. The queue constrains the upstream section in both.
- **Parallel pipes to parallel resistor network: grade 2.** Pump to battery, manifold to split junction, pipe A and B
  to r1 and r2, header to join junction. Conservation at nodes corresponds to Kirchhoff's current law.
- **Pipes in series: grade 0 (lookalike).** Same nodes, but the split into two branches is replaced by one path.
- **Suspension to series RLC circuit: grade 2.** Mass to inductor, spring to capacitor, shock absorber to resistor.
  Exchange between two stores plus dissipation gives damped oscillation.
- **Flour stock to float valve tank: grade 2.** Stock level sensed to close its own inflow.
- **Flour stock with weekly report: grade 0 (lookalike).** The counter feeds a report, so the inflow is never
  closed by the level.

## Recording a label

For every label record:

- `system_id`: the candidate id from `data/seed_knowledge` or `data/mechanisms`.
- `grade`: 2, 1 or 0.
- `rationale`: two to four sentences naming the role mapping used and the main reason for the grade. For grade 0
  say which check fails.
- `role_mapping`: object mapping query node ids to candidate node ids. Empty for grade 0 entries where no mapping
  was found. Merged nodes may map to the same candidate node.
- `lookalike` and `lookalike_reason` as above.
- `label_status`: `author_labelled` until another person has re-graded it, then `independent_reviewed` in the review
  file (the original label is not overwritten).
- `independent_review`: `none` until a reviewer has filled in `review_template.json`.

## Unlabelled candidates

A candidate with no label has not been judged. The evaluator treats unlabelled candidates as grade 0 for ranking
metrics, which can penalise a genuine analog that the author did not think of. Reviewers should flag any such
candidate they find in the `comment` field of the review file.

## Process rules

- Write labels from this guide, before running any matcher on the query set.
- After the first evaluation run, labels are not edited except by a logged amendment in `docs/benchmark-notes.md`
  (what changed, why, and the hash of the commit).
