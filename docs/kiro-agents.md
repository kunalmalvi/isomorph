# Kiro Agent Responsibilities

Agents work from specs in `.kiro/specs`, follow `.kiro/steering`, and are checked by `.kiro/hooks`.

| Agent | Owns | Reads | Must not |
|---|---|---|---|
| Planner | docs/implementation-plan.md, specs, task state | all docs | write product code |
| Engine agent | backend/intelligence, backend/experiments | structural-dna-engine, cross-domain-discovery, mapping-and-transformation, hypothesis-and-validation specs | import api or database from the engine |
| Knowledge agent | backend/knowledge_base, data/, scripts/validate_seed_data.py | database-knowledge-architecture spec, data-integrity steering | add rows without a source |
| API agent | backend/api, backend/services, backend/database | backend-api-contracts spec, docs/api-contracts.md | put business logic in routers |
| Frontend agent | frontend/ | frontend-design-system spec, ui-design-system steering | add controls without a backend action |
| QA agent | backend/tests, frontend tests, CI | testing-and-deployment spec, testing-requirements steering | claim verification that did not run |
| Docs agent | README.md, docs/ | all | use em dashes or overstate verification |

## Hooks
- tests-on-change: runs the pytest suite after Python edits.
- format-and-typecheck: ruff and tsc where installed.
- broken-imports: compileall and layer import check.
- api-contract-validation: routers versus docs/api-contracts.md.
- migration-check: model changes need a reversible migration and docs entry.
- docs-update: keeps docs and specs aligned with behavior.

## Handoff protocol
Each agent records findings (environment issues, deviations, skipped tests) in the task feature file before handing off.
