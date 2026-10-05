# CVT Simulator backend

This service is an HTTP/application adapter around CINDER. It does not own CVT
mechanics, formulas, parameter aliases, display-unit conversion, graph layout,
or 3D geometry reconstruction.

## Boundary

```text
FastAPI routes → application services → cinder_gateway → CINDER public contracts
```

`app/application/cinder_gateway.py` is the only backend module with direct
`cinder.*` imports. Routes and storage operate on plain JSON-safe public
documents and projections.

The database layer follows the same boundary. It stores user-facing, versioned
objects that can resolve into CINDER's public simulation case, but it does not
move mechanics into the backend:

```text
EngineVersion          → input_boundary
CVTDesignVersion       → assembly
OutputSystemVersion    → output_boundary template
LoadCase               → scenario + output-boundary overrides
ExecutionPreset        → execution
Run                    → frozen full cinder_simulation_case snapshot + stored result
```

## M1 accounts and application foundation

See [M1_APPLICATION_FOUNDATION.md](../docs/M1_APPLICATION_FOUNDATION.md) for local signup,
password-reset mail, existing-user credential setup, ownership rules, deployment
configuration, and coding standards. Private API routes require a session and CSRF
header; old examples that submit account/user IDs must use the authenticated client.

## M2 physical library

See [M2_PHYSICAL_LIBRARY.md](../docs/M2_PHYSICAL_LIBRARY.md) for the engine, belt,
CVT, and vehicle editors; immutable revisions and pinned updates; additive samples;
optional development fixtures; measurement conventions; and verification record.
Upgrade with `alembic upgrade head` before seeding an existing database.

## M3 experiments and durable jobs

See [M3_EXPERIMENTS_AND_JOBS.md](../docs/M3_EXPERIMENTS_AND_JOBS.md) for named tune/scenario
revisions, the road editor contract, queue/notification behavior, resource limits,
migration precautions and the verification record. Every simulation submission
now requires an idempotency `request_key` and executes in a separate durable worker.

## M4 results and public configurations

See [M4_RESULTS_AND_PUBLIC_LIBRARY.md](../docs/M4_RESULTS_AND_PUBLIC_LIBRARY.md) for
searchable run history, exact exports, frozen experiment copying, fixed publication
bundles, explicit dependency consent and independent copies. Migration `20261004_0008`
adds publication/copy history without modifying existing scientific records.

The [demo and worker follow-up](../docs/DEMO_AND_WORKER_TROUBLESHOOTING.md) adds an
anonymous recorded demo and portable memory monitoring. Install the updated
requirements before restarting the worker; its new dependency is `psutil`.

## CVT-owned tunes and component previews

See [CVT_TUNES_AND_PLAYBACK_CURSOR.md](../docs/CVT_TUNES_AND_PLAYBACK_CURSOR.md)
for the CVT-owned tune workflow, per-version defaults, shared editor and mechanism
previews, and the playback cursor fix. Run `alembic upgrade head` before restarting
this update: migration `20261005_0010` moves existing tunes to their CVT references
and initializes defaults while retaining saved run inputs.

## Local development

From `backend/`:

```bash
python -m venv venv
venv\Scripts\activate             # macOS/Linux: source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

alembic upgrade head
python -m app.scripts.init_database
uvicorn app.main:app --reload
```

On Linux/macOS, start `python -m app.scripts.run_worker` in another backend
terminal with the same environment/database. On Windows, use the Docker setup
below for both API and worker. Without a worker, simulations stay queued.

### Windows / Docker Desktop setup

Start Docker Desktop with Linux containers enabled. Run the following commands
from the **repository root**, where `backend/Dockerfile` exists. In PowerShell:

```powershell
cd F:\Code\Projects\CVT-Simulator
```

In Command Prompt, use `cd /d F:\Code\Projects\CVT-Simulator` to change drives too.
The remaining Docker commands work in either shell. The API and worker must share
the same volume and database URL.

First setup:

```powershell
docker build -f backend/Dockerfile -t cinder-local .
docker volume create cinder-local-data
docker run --rm -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local alembic upgrade head
docker run --rm -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local python -m app.scripts.init_database
docker run -d --name cinder-local-api -p 8000:8000 -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local
docker run -d --name cinder-local-worker -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local python -m app.scripts.run_worker
```

After applying a code update, rebuild and recreate **both** containers. Restarting
an old container does not install the new image. These commands preserve accounts
and runs in the existing volume; retain your existing volume/database settings if
you use different names.

```powershell
docker stop cinder-local-api cinder-local-worker
docker rm cinder-local-api cinder-local-worker
docker build -f backend/Dockerfile -t cinder-local .
docker run --rm -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local alembic upgrade head
docker run --rm -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local python -m app.scripts.init_database
docker run -d --name cinder-local-api -p 8000:8000 -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local
docker run -d --name cinder-local-worker -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local python -m app.scripts.run_worker
```

Normal reseeding adds missing defaults, including the demo course. It does not
require `--reset`. The playback/force update introduces no new database migration.

In a frontend terminal, with Node installed:

```powershell
cd F:\Code\Projects\CVT-Simulator\frontend
npm ci
npm run dev
```

Frontend startup regenerates API types using `backend/venv/Scripts/python.exe`
(on Windows), so keep that virtual environment and its backend dependencies
installed. Alternatively, export the contracts with Docker before starting the
frontend; this PowerShell variant needs no host Python environment:

```powershell
cd F:\Code\Projects\CVT-Simulator
New-Item -ItemType Directory -Force backend/generated | Out-Null
docker run --rm --mount "type=bind,source=$($PWD.Path)/backend/generated,target=/contracts" cinder-local python -m app.scripts.export_contract_artifacts --output-dir /contracts
cd frontend
$env:CINDER_SKIP_BACKEND_EXPORT = "1"
npm run dev
```

Repeat the Docker export after backend/API changes if using that alternative.
Open `http://localhost:5173` or `http://localhost:5173/demo` for anonymous playback.

Useful diagnostics (Ctrl+C exits log following):

```powershell
docker ps -a
docker logs --tail 100 cinder-local-api
docker logs --tail 100 -f cinder-local-worker
```

A missing Docker engine pipe means Docker Desktop is not running. A missing
`backend` path means the shell is not at the repository root. Child exit 125 logs
the expected and observed parent IDs; rebuild/recreate the worker to install the
PID-1 startup fix. No database reset is needed for that fix.

`requirements.txt` installs the bundled `../cvtModel` source (currently
CINDER 1.1.5.dev0) alongside backend dependencies. Run installation from
`backend/`. This reporting update exposes signed sheave balances and solver
accelerations; it does not change the integration equations. Local and Docker
installations use the same source, and run provenance retains its package version.
`requirements-dev.txt` extends that list with developer tooling. After pulling
changes to `cvtModel/`, reinstall requirements or rebuild both containers.

The API is served at `http://localhost:8000/api/v1`; Swagger UI is at
`http://localhost:8000/docs`.

## Database setup

The database stores library objects, immutable experiment revisions and durable
jobs. `POST /api/v1/experiments/runs` resolves the current experiment and freezes it;
`POST /api/v1/runs/from-library` retains the legacy selection adapter. Both return
202 after admission. A standalone worker persists summaries, previews and full
results. Direct/debug and validation submissions use the same queue and limits.
New jobs do not reuse the legacy global cache; existing artifacts stay readable.

### Option A: local SQLite database

Run initialization, the API and the worker from `backend/`, using the same
`CVT_DATABASE_URL`. The default SQLite filename is relative to the working
directory. The worker checks for missing tables/columns and an unreadable schema
before claiming jobs; it prints the database location when setup is incomplete.

```bash
python -m app.scripts.init_database
```

This creates `./cvt_simulator_dev.db` and inserts deterministic public defaults:

- a Baja SAE school catalog for signup and author filters;
- one seed account (create your own account to sign in);
- one Kohler CH440 (Baja Restricted) engine;
- one McMaster 2025 CVT using the Enduro 100 belt;
- one McMaster 500 lb vehicle setup and its output system;
- manufacturer/series belt choices and baseline/paper-inspired CVT tunes;
- flat, constant-angle, climb/descent and whoops load cases;
- the 160 m McMaster demonstration course used by anonymous playback;
- one execution preset.

The demonstration course is 30 m flat, 30 m at +35°, 10 m flat, 30 m at −35°,
10 m flat, 20 m at +20°, then 30 m flat. Distances are measured along the road;
course mode stops at the finish. Its retained playback was produced by a real
simulation with the same road definition as the seeded load case.

Seeding adds missing samples and reconciles the curated default catalog. User
objects and runs are retained. Optional `--development-fixtures` adds clearly
labeled isolated accounts and queued/failed/cancelled examples; it never
fabricates simulation results.

Use a custom SQLite path if desired:

```bash
python -m app.scripts.init_database --database-url sqlite:///./scratch.db
```

For a disposable development database that needs a fresh start, **stop the API,
every worker and any database browser first**, then run:

```bash
python -m app.scripts.init_database --reset
python -m app.scripts.run_worker --once
```

This deletes accounts, saved configurations and runs, then recreates the seeded
workspace. It removes the database together with SQLite's `-journal`, `-wal` and
`-shm` files. Reset refuses when it detects an open database handle and prints its
process ID. This check is best effort: OS permissions can hide handles, and a
process could start after the check. Keep all clients stopped until seeding
finishes. Never delete only a journal when trying to preserve existing data.

`malformed database schema ... index ... already exists` during a SELECT indicates
an unreadable SQLite schema; it does not by itself show that an Alembic migration
tried to create the index twice. A later `no such table: runs` means that connection
sees an uninitialized or incomplete database. These messages alone cannot tell
whether the file was replaced or the configured path changed. The reset above is
the supported recovery for disposable development data. Restart the API and the
long-running worker only after it succeeds. No reset is needed for a healthy
database just to install this maintenance fix.

### Option B: Postgres

```bash
export CVT_DATABASE_URL='postgresql+psycopg://cvt:cvt@localhost:5432/cvt_simulator'
alembic upgrade head
python -m app.scripts.init_database
```

The app also reads these optional environment variables:

```text
CVT_DATABASE_URL   SQLAlchemy URL, default sqlite:///./cvt_simulator_dev.db
CVT_DATABASE_ECHO  set to 1/true/yes for SQL logging
```


### Payload storage

Reusable design objects use a relational shell with JSON payload bodies:

```text
relational columns: ownership, visibility, lifecycle, catalog priority, released version
JSONB payloads: input_boundary, cinder_assembly, output_boundary_template, load cases, runs
```

The SQLAlchemy payload type maps to PostgreSQL `JSONB` and falls back to regular
`JSON` on SQLite so tests stay lightweight. This keeps CINDER-facing model
fragments queryable and indexable on Postgres without over-normalizing every
future actuator, engine-map, gearbox-loss, tire, or suspension variant.

### Schema lifecycle

Alembic owns production migrations:

```bash
alembic upgrade head
```

Back up first and stop/drain pre-M3 API processes for the first M3 upgrade. The M3
downgrade refuses to delete history: restore the verified backup and compatible
application instead. See the milestone document for the exact migration behavior.

For unit tests and disposable SQLite files, `app.database.bootstrap.create_database`
uses the ORM metadata directly. Production databases should always advance through
Alembic. Revision `20260907_0003` adds independent CINDER result-contract version
tracking while preserving the existing input-schema column.

## Database design notes

The persistence model separates subscription/workspace concerns from Baja school
affiliation:

```text
Account.tier                       billing/capabilities
Institution                        school/university/company list
AccountInstitutionAffiliation      optional self-reported school/team identity
```

There is no institution validation in V1. Seeded institutions are just a
convenient list for filters and attribution.

The drivetrain/gearbox side lives in `OutputSystemVersion.output_boundary_template`,
not the CVT design. The current simplified output system supports fields like:

```json
{
  "kind": "locked_final_drive_vehicle",
  "final_drive": {
    "reduction_ratio": 7.556,
    "wheel_radius_m": 0.2794
  },
  "direct_secondary_shaft_inertia_kg_m2": 0.05,
  "drivetrain_loss_model": {"kind": "none"}
}
```

That gives the future efficiency hook a clean home without prematurely creating a
separate gearbox-library object. Later, the loss model can become
`constant_efficiency`, `ratio_curve`, or a torque/speed map without changing CVT
ownership.

## Production container

Build from the repository root:

```bash
docker build -f backend/Dockerfile -t cvt-simulator-api .
docker run --rm -p 8000:8000 cvt-simulator-api
```

The container builds CINDER from `cvtModel/` in this checkout through the same
`requirements.txt` used locally. Rebuild and recreate both API and worker
containers together when that source changes.

The backend preset files are copied with `backend/`; for example, the tuned
launch preset is available at `/app/presets/baja-launch-baseline.json` inside
the image.

To confirm the image contains the expected preset:

```bash
docker run --rm cvt-simulator-api python -c "from pathlib import Path; print((Path('/app/presets') / 'baja-launch-baseline.json').is_file())"
```

## Black-box API testing

The scripts below predate M3's required request keys, authentication and durable
worker contract. They are not current passing coverage. Per the implementation
baseline, adaptation and committed E2E/CI integration are deferred to M5; see the
M3 verification record for the focused checks performed during implementation.

A manual end-to-end test plan is included in [`docs/BLACK_BOX_TESTING.md`](docs/BLACK_BOX_TESTING.md). It covers seeded library data, draft/release/fork/archive flows, library-resolved runs, direct-run comparison, cache reuse, preview artifacts, and full-result eviction/regeneration expectations.

For the automated version of the same flow, run:

```bash
python -m app.scripts.smoke_library_database
```

## Main endpoints

```text
GET  /api/v1/health
GET  /api/v1/metadata/runtime
GET  /api/v1/metadata/conventions
GET  /api/v1/metadata/catalog
GET  /api/v1/metadata/editor-schema
GET  /api/v1/metadata/simulation-case-schema
GET  /api/v1/presets
GET  /api/v1/presets/{preset_id}
GET  /api/v1/library/institutions
GET  /api/v1/library/{engines|cvt-designs|output-systems|vehicle-assemblies}
POST /api/v1/library/{engines|cvt-designs|output-systems|vehicle-assemblies}
PATCH /api/v1/library/{resource}/{object_id}/draft
POST /api/v1/library/{resource}/{object_id}/release
POST /api/v1/library/{resource}/versions/{version_id}/fork
POST /api/v1/library/{resource}/versions/{version_id}/deprecate
POST /api/v1/library/{resource}/{object_id}/archive
GET /api/v1/library/tunes                 legacy reads; POST/PATCH return 410
GET/POST/PUT /api/v1/experiments/*         revisioned tunes and scenarios
POST /api/v1/experiments/road/resolve
POST /api/v1/experiments/preview
POST /api/v1/experiments/runs             freeze and queue an experiment
GET/POST/PATCH /api/v1/library/load-cases
GET/POST/PATCH /api/v1/library/execution-presets
POST /api/v1/simulation-cases/validate
POST /api/v1/studies/geometry/endpoint-radii
POST /api/v1/studies/geometry/target-ratios
POST /api/v1/studies/actuation/clamping-response
POST /api/v1/runs                         direct full-contract debug run
POST /api/v1/runs/from-library            resolve released DB objects and persist run
POST /api/v1/runs/{run_id}/rerun          rerun a persisted run from frozen input
GET  /api/v1/runs                         list persisted library runs
GET  /api/v1/runs/{run_id}
GET  /api/v1/runs/{run_id}/input
GET  /api/v1/runs/{run_id}/preview
GET  /api/v1/runs/{run_id}/result
GET  /api/v1/runs/{run_id}/forces          stopped runs only; projected contact vectors
GET  /api/v1/demo                         retained anonymous playback
GET  /api/v1/demo/forces                  anonymous projected contact vectors
POST /api/v1/runs/{run_id}/cancel
GET  /api/v1/runs/activity
POST /api/v1/runs/notices/{notice_id}/read
```

Static engineering studies still return synchronously. Simulations all use the
durable queue, with one queued/running job per account. Reruns create new records
from frozen input. States are `queued`, `running`, `completed`, `failed`,
`timed_out` and `cancelled`; the legacy `validating` transport value remains
readable. There is no invented percentage progress.

## Type generation

```bash
python -m app.scripts.export_contract_artifacts --output-dir generated
```

This writes:

- `generated/openapi.json` for endpoint/request/response TypeScript types;
- `generated/cinder_simulation_case.schema.json` for the canonical nested
  `SimulationCaseDocument` TypeScript type.

Use generated types in the frontend; do not create a parallel parameter map.

## Tests and formatting

```bash
python -m pytest
python -m app.scripts.smoke_library_database
flake8 app test
black --check app test
```

`app.scripts.smoke_library_database` is an intentionally broad integration
smoke test. It boots a temporary SQLite-backed API, seeds demo data, then walks
through create/update/release/fork/deprecate/archive flows plus tune, load-case,
and execution-preset creation.
