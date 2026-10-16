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

`/demo/sliding-block` is a public geometry inspection page for one synthetic
curved-cup/linear-ramp primary. It needs the API, but no worker or account.
The API caches 241 CINDER finite-profile study poses across the configured stroke
(15 mm by default). The 3D assembly
and axial section select the same frame; playback is a geometry scrub, while
the displayed reactions are evaluated at held closure and 2,500 rpm.
Cup and sheave backing is representative hardware. The block's circular cup
face and flat ramp face define its smooth extruded solid, uniform-steel mass,
COM and tensor. Display tessellation does not change those mass properties.
One slope defines both mating flat faces; their contact span is highlighted.
The normal arrow indicates direction, not pressure location or distribution.
The study reports held force resultants from CINDER's geometry inspection.
The CINDER 1.2 simulation provider rejects conformal face contact, so the page
explicitly reports that it is not simulation-ready and does not report a
unique guide couple. No endpoint representative or contact-only moment from
the inspection utility is presented as a physical load location or full torque.
Select the block, reaction cup or movable ramp in the equal-scale section,
or choose Stroke, then edit its unit-aware dimensions. A 350 ms debounce
refreshes both views through `POST /api/v1/demo/sliding-block/preview`.
Undo/redo and Reset dimensions include incomplete quantity drafts. The last
preview stays visibly stale while a newer edit is pending or cannot make
contact; stale/invalid loads are hidden. Late responses cannot replace newer
edits. Contact-valid geometry with hardware interference is displayed with
the colliding bodies outlined in red at the current closure.

The thicker default uses a 40 mm block datum thickness and clears all three
cup/sheave pairings. A polygon translation sweep checks the complete moving
hardware path between frames, and the UI reports the minimum section gap.
The cup/ramp touching threshold is computed from their actual rim geometry;
it is not a universal minimum block size. The 52 mm open body-datum radius is
fixed in this synthetic construction; edits rebuild the contacting assembly
at that reference. This is not an import/calibration tool for measured parts.

Preview inputs and frame count are bounded, successful results use a 16-entry
cache, expensive requests have a per-worker two-slot limit, and the existing
database-backed IP throttle limits submissions to 90 per minute. No preview
is saved or submitted to a worker. Physical-library saving remains follow-up work.
The belt is local groove context, rather than a solved belt loop. Dashed 3D
tracks continue across removed hardware in cutaway mode. Regression browser
checks consume the CINDER-generated sample exported with the contract artifacts.
Hardware sweep checks use tessellated meridional sections; weight/contact
inspection uses the exported poses. Circumferential contact
and whole-solid 3D clearance are illustrative, as in the underlying 2D model.

The [mechanism input design](docs/mechanism-input-design.md) compares dimensioned
templates, constrained sketching, measured points and CAD import, and proposes
the remaining editor, mass-property, validation and preview contracts for the next PRs.

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
