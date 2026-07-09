# CVT Simulator frontend

The frontend is a Vite/React single-page application using the database-backed CVT Simulator API. Normal runs resolve seeded/released library objects instead of posting raw CINDER documents from the UI.

## Local development

From `frontend/`:

```powershell
Copy-Item .env.example .env
npm ci
npm run dev
```

`.env` points the Vite development server directly at the backend:

```text
VITE_API_BASE_URL=http://localhost:8000
VITE_DEMO_USER_ID=00000000-0000-4000-8000-000000000001
VITE_DEMO_ACCOUNT_ID=00000000-0000-4000-8000-000000000002
```

The demo IDs are the explicit local-development rows seeded by `python -m app.scripts.init_database`. They are test/demo defaults only; real auth should replace that configuration boundary later.

The API client already names routes such as `/api/v1/library/*` and `/api/v1/runs/from-library`; do **not** add `/api/v1` to `VITE_API_BASE_URL`.


## Current product flow

The app intentionally exposes a narrow V1 run setup:

```text
seeded released Baja vehicle assembly (500 lb default or 400 lb lightweight)
  -> selected tune
  -> selected load case (flat, 20° hill, or ~10 s flat-to-30° route-intent seed)
  -> selected execution preset
  -> POST /api/v1/runs/from-library
  -> GET /api/v1/runs/{run_id}/result for playback
```

Engine and CVT hardware editing are hidden until dedicated database object editors exist. The current vehicle dropdown switches between seeded output-system masses only. The legacy direct `POST /runs` contract path remains backend/debug-only and is not part of the normal frontend flow.

Useful checks:

```powershell
npm run lint
npm run build
```

When the backend OpenAPI contract changes, regenerate and commit the generated types:

```powershell
npm run contracts:generate
```

## Production container

The production image serves the static Vite build with nginx. It calls the backend through same-origin `/api/v1/*` requests, so no browser-visible backend hostname or CORS configuration is needed in the container deployment.

Build from the repository root:

```powershell
docker build -f frontend/Dockerfile -t cvt-simulator-frontend frontend
```

The frontend and backend containers must share a Docker network, and the backend container/service must be named `cvt-backend`:

```powershell
docker network create cvt-simulator

docker run -d --name cvt-backend --network cvt-simulator -p 8000:8000 cvt-simulator-backend

docker run --rm --name cvt-frontend --network cvt-simulator -p 8080:80 cvt-simulator-frontend
```

Open `http://localhost:8080`. The frontend health endpoint is available at `/health`; backend documentation is proxied at `/docs`.

## Build-time API override

The default container build intentionally leaves `VITE_API_BASE_URL` blank, which makes the browser use its own origin and nginx proxy `/api/v1/*` to `cvt-backend`.

For a deployment where the API is deliberately hosted at a separate public origin, supply the origin at image-build time:

```powershell
docker build -f frontend/Dockerfile `
  --build-arg VITE_API_BASE_URL=https://api.example.com `
  -t cvt-simulator-frontend frontend
```

Do not use runtime environment variables for `VITE_API_BASE_URL`; Vite embeds `VITE_*` values while building the static files.
