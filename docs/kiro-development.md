# How ISOMORPH was developed with Kiro

The project was planned and built through Kiro style specs, steering files, hooks and delegated agents.

## Specs (`.kiro/specs`)
Ten specs, each with `requirements.md`, `design.md` and `tasks.md`: product requirements, structural DNA engine, cross-domain discovery, mapping and transformation, hypothesis and validation, database and knowledge architecture, backend API contracts, frontend design system, and testing and deployment. The work was split into four features: planning docs and Kiro files, the stdlib engine, the service layer, and the frontend with deployment files.

## Steering (`.kiro/steering`)
Always-on rules: product vision (hypotheses not proofs, provenance on every claim), architecture layering (the engine never imports the API or database layers), coding conventions, data integrity (no seed row without a source) and testing requirements (never claim verification that did not run).

## Hooks (`.kiro/hooks`)
| Hook | Purpose |
|---|---|
| tests-on-change | Run the pytest suite after Python edits |
| format-and-typecheck | ruff and tsc where installed |
| broken-imports | compileall and layer import check |
| api-contract-validation | Routers versus `docs/api-contracts.md` |
| migration-check | Model changes need a reversible migration and a docs entry |
| docs-update | Keep docs aligned with behavior |

## Agent roles
See [kiro-agents.md](kiro-agents.md). Each handoff recorded findings in the feature file under `.agents/tasks/task-isomorph-platform/features`.

## What this process caught
- The sandbox had no package index, so the engine was written in the standard library, and tests that need FastAPI or SQLAlchemy skip with a stated reason.
- During frontend work the CORS configuration allowed GET, POST, PATCH and DELETE but not PUT, which the stage edit endpoint uses. A browser on another origin would have been blocked, so PUT was added in `backend/api/main.py`.
- The server does not apply saved default weights, so the UI says so and the Advanced form sends the weights explicitly.
