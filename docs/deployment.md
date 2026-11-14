# Deployment

Status: UNVERIFIED. The compose file and Dockerfiles were written in a sandbox where Docker could not run. Treat the first deployment as a test of these files.

## Components
| Component | Image or process | Port | Notes |
|---|---|---|---|
| Database | `pgvector/pgvector:pg16` | 5432 (internal) | Volume `pgdata`. Set `USE_PGVECTOR=false` if you use a Postgres without pgvector |
| Backend | `backend/Dockerfile` (python 3.12 slim, non-root) | 8000 | Runs `alembic upgrade head` then uvicorn. Health: `GET /api/v1/health` |
| Frontend | `frontend/Dockerfile` (node 22 alpine, standalone output, non-root) | 3000 | `NEXT_PUBLIC_API_URL` is a build argument |

## Steps
1. `cp .env.example .env`.
2. Set `POSTGRES_PASSWORD` to a strong value (compose refuses to start without it).
3. Set `ISOMORPH_SECRET_KEY` to at least 32 random characters, for example `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`. With `ISOMORPH_ENV=production` the backend refuses to start on the built-in development key.
4. Set `CORS_ORIGINS` to the exact frontend origin, for example `https://isomorph.example.com`.
5. Set `NEXT_PUBLIC_API_URL` to the public API URL including `/api/v1`, then `docker compose up --build -d`.
6. Open the frontend, register the first account and run a discovery.

## Production checklist
- Put both services behind TLS (a reverse proxy such as Caddy or nginx).
- Do not publish the database port. The compose file does not.
- Back up the `pgdata` volume before running `alembic downgrade`.
- Remote AI keys belong in the environment or a secret manager, never in the image or the repository.
- The rate limiter and job runner are per process. Run a single backend replica, or accept that limits are per replica and that a restart leaves in-flight runs `queued` or `running`.
- Registration is open. Restrict it at the proxy if the instance is not public.
- The frontend stores the access token in `localStorage`. Serve it with a strict Content Security Policy at the proxy, because an XSS bug would expose the token.
- Uploads are capped by `MAX_UPLOAD_BYTES` (5 MiB default). Match the proxy body limit.
- Server sent events need proxy buffering off. The API sends `X-Accel-Buffering: no`. For other proxies disable response buffering on `/api/v1/discoveries/*/events`.

## Checks after deploying
1. `curl -f http://localhost:8000/api/v1/health` returns `{"status":"ok"}`.
2. `docker compose logs backend` shows the migration finishing without errors.
3. Run the flagship flow in [demo-script.md](demo-script.md).
4. On a development machine, run the full backend test suite with dependencies installed and expect zero skips.
