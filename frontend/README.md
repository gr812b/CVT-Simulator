# CVT Simulator frontend

The frontend is a Vite/React single-page application using only the CINDER v1 API.

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
```

The API client already names routes such as `/api/v1/presets` and `/api/v1/runs`; do **not** add `/api/v1` to `VITE_API_BASE_URL`.

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
