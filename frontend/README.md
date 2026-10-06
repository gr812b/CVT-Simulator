# CVT Simulator frontend

The frontend is a Vite/React application with Mantine controls, generated API
contracts, and Three.js previews. It presents a public physical library, CVT-owned
tunes, reusable load cases, a guided run builder, and stored results/playback.
Sign in to save or copy items and submit simulations. Saved content is public;
account email and credentials are private.

## Development

Use Node.js 22. First install the [backend dependencies](../backend/README.md)
and start its API. From `frontend/`:

```bash
npm ci
npm run dev
```

Open `http://localhost:5173`. The Vite proxy forwards `/api` to port 8000.
The default `VITE_API_BASE_URL` is empty, giving the browser same-origin cookies
and CSRF handling. Copy [.env.example](.env.example) to `.env` only if overriding
settings. API clients already include `/api/v1`; an override must be an origin
such as `https://api.example.com`, not an origin with that prefix appended.

The backend worker must share the API's database to process new runs. `/demo`
plays a retained recording and does not need a worker or account.

## Run and tune behavior

Build a run selects a vehicle, CVT/belt, primary boundary, tune and load case.
Saving a tune selects the returned ID, revision and values for the run. Saving
setup changes or choosing another vehicle with the same CVT preserves that tune;
changing the CVT requires a compatible tune. **Use for this run only** keeps the
edit in the submitted configuration without saving a library tune.

A run freezes its configuration when submitted. Later library edits cannot
change that run. **New experiment from this run** reopens saved references and
run-only overrides without creating library copies. **Rerun frozen inputs**
submits another job from the saved input. Activity and run pages show persisted
status, cancellation and completion notices.

The tune preview samples contact while editing. Save performs independent full
validation and can reject a draft that passed the sampled preview. Invalid,
stale or incomplete previews must not enable submission.

`primary_tip_mass` is a per-flyweight tip mass, excluding the arm/body and
independent of flyweight count; its maximum is 500 g per tip. When scene metadata
identifies a uniform arm plus concentrated tip, the illustrated tip-cylinder
lengths scale with mass around a fixed centre. Legacy/other distributions retain
the fallback illustration. Drawing dimensions do not alter solver geometry.

## Generated contracts

`npm run dev` and `npm run build` generate types from backend OpenAPI and CINDER's
assembly, simulation-case and result schemas. The exporter uses `backend/venv`
when present, `CINDER_BACKEND_PYTHON` when explicitly set, or system Python.
To regenerate manually:

```bash
npm run contracts:generate
```

Generated files under `src/api/generated/` and `backend/generated/` are not
committed. For Docker-only Python or pre-exported CI schemas, see the
[backend contract-export instructions](../backend/README.md#linux-containers-on-windows-or-other-hosts).
`CINDER_BACKEND_ARTIFACTS` can select a schema directory;
`CINDER_SKIP_BACKEND_EXPORT=1` uses existing exported files without refreshing.
Refresh them when the backend or model contracts change.

Use feature clients and `api/transport.ts` for session/CSRF handling, shared
`QuantityInput` controls for quantities, and `styles/theme.ts` for presentation.
Do not duplicate generated request types or mechanics formulas in the UI.

## Checks

From `frontend/` after `npm ci`:

```bash
npm run lint
npm run build
npm run test:helpers
npx playwright install chromium
npm run test:browser
```

`npm test` runs both test groups after the browser is installed.
`test/frontend_checks.mjs` covers pure helpers and JSX adapters; it is not a React
browser test or a replacement for the TypeScript build.
`test/run_builder_tune_browser.mjs` renders the real React/Mantine run builder and
tune dialog with deterministic API/unrelated-editor adapters. It checks saved
revision selection, public-tune copying, setup/CVT changes, rejected saves and
run-only edits through preview/submission. Set `CHROMIUM_PATH` to an existing
compatible executable if the managed browser is unavailable. These tests do not
replace a real backend/CINDER acceptance run.

## Production

The image serves the Vite build with nginx and proxies `/api` to `cvt-backend`.
Use the [root Compose deployment](../README.md#production-deployment) for the API,
worker, PostgreSQL and networking. The frontend health endpoint is `/health`;
`/docs` proxies the backend API reference.

Build from the repository root with
`docker build -f frontend/Dockerfile -t cvt-simulator-frontend .`.
For a deliberately separate API origin, add
`--build-arg VITE_API_BASE_URL=https://api.example.com` and configure backend CORS
for the frontend origin. Vite embeds this value at build time; changing a running
container's environment does not rewrite the static bundle.
