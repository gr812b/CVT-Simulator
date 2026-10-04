# CVT Simulator frontend

The frontend is a Vite/React application using authenticated, generated API contracts.
See [M1 standards](../docs/M1_APPLICATION_FOUNDATION.md), [M2 physical editors](../docs/M2_PHYSICAL_LIBRARY.md),
and [M3 experiments/jobs](../docs/M3_EXPERIMENTS_AND_JOBS.md) for the current baseline.

## Local development

From `frontend/`:

```powershell
Copy-Item .env.example .env
npm ci
npm run dev
```

The default Vite development proxy sends `/api` to port 8000. Leave the API origin
blank for same-origin cookies and CSRF handling:

```text
VITE_API_BASE_URL=
```

Create/sign into an account; identity is derived from its server session. There
are no configured demo user/account IDs. Start both the backend API and
`python -m app.scripts.run_worker` with the same database. Simulations stay queued
if the worker is absent; it requires POSIX or the Linux backend container.

The API client already names routes such as `/api/v1/library/*` and `/api/v1/runs/from-library`; do **not** add `/api/v1` to `VITE_API_BASE_URL`.


## Current product flow

The physical library owns reusable engine, belt, CVT and vehicle setup revisions.
Tune & run selects an exact setup revision, edits a named tune and reusable road
scenario, and explicitly runs unsaved values or saves a tune before running.
The road editor supports feature sections, whoops, draggable/exact points and
undo/redo. Every normal run is frozen and queued through `/experiments/runs`.
Activity shows persisted notifications, status/cancellation and recent results;
`/playback?run=<id>` reloads a saved result. Dashboard/demo shortcuts use the same
durable queue through the legacy library selection adapter.

API types derive from generated OpenAPI/CINDER schemas. Use shared feature
clients and `api/transport.ts`, Mantine controls, `QuantityInput`, and the central
`styles/theme.ts`; do not duplicate transport types or scatter theme values.

Useful checks:

```powershell
npm run lint
npm run build
```

API/CINDER TypeScript contracts are generated build artifacts and are not committed.
`npm run dev` and `npm run build` refresh them automatically. The generator uses
`backend/venv` when available (or `CINDER_BACKEND_PYTHON` / system Python) to
export backend OpenAPI plus CINDER assembly, simulation-case, and
simulation-result schemas before generating TypeScript.

You can still regenerate explicitly when debugging the contract boundary:

```powershell
npm run contracts:generate
```

## Production container

The production image serves the static Vite build with nginx. It calls the backend through same-origin `/api/v1/*` requests, so no browser-visible backend hostname or CORS configuration is needed in the container deployment.

Build from the repository root:

```powershell
docker build -f frontend/Dockerfile -t cvt-simulator-frontend .
```

Use the repository's Compose deployment: it supplies PostgreSQL, the migrated
API, the durable worker, and the frontend on the correct networks. The nginx
upstream remains `cvt-backend`. The frontend health endpoint is `/health`;
backend documentation is proxied at `/docs`.

## Build-time API override

The default container build intentionally leaves `VITE_API_BASE_URL` blank, which makes the browser use its own origin and nginx proxy `/api/v1/*` to `cvt-backend`.

For a deployment where the API is deliberately hosted at a separate public origin, supply the origin at image-build time:

```powershell
docker build -f frontend/Dockerfile `
  --build-arg VITE_API_BASE_URL=https://api.example.com `
  -t cvt-simulator-frontend .
```

Do not use runtime environment variables for `VITE_API_BASE_URL`; Vite embeds `VITE_*` values while building the static files.
