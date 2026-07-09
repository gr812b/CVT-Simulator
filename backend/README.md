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

## Local development

From `backend/`:

```bash
python -m venv venv
venv\Scripts\activate             # macOS/Linux: source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

`requirements.txt` is the local-development entry point. It installs CINDER
from the sibling `../cvtModel` directory in editable mode, so CINDER source
changes are available immediately without rebuilding a package.

The API is served at `http://localhost:8000/api/v1`; Swagger UI is at
`http://localhost:8000/docs`.

## Database setup

The database is wired into library/object-management endpoints and the
resolver-backed run endpoint. `POST /api/v1/runs/from-library` accepts released
database object IDs, freezes the resolved CINDER contract, executes the run,
stores permanent summaries, a durable downsampled preview artifact, an evictable
full-result artifact, and reuses cached results. The original `POST /api/v1/runs`
direct-contract endpoint remains available for debugging and comparison.

### Option A: local SQLite database

```bash
python -m app.scripts.init_database
```

This creates `./cvt_simulator_dev.db` and inserts deterministic seed data:

- Baja-oriented institutions such as McMaster, Cornell, Virginia Tech, WVU, and RIT;
- one demo account/user;
- one official/default seeded engine boundary;
- one default seeded CVT hardware design;
- one default seeded output system with gearbox/final-drive data owned outside the CVT;
- one default vehicle assembly pinning the released versions;
- one tune, one flat-launch load case, and one execution preset.

Use a custom SQLite path if desired:

```bash
python -m app.scripts.init_database --database-url sqlite:///./scratch.db
```

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
alembic downgrade -1
```

For unit tests and disposable SQLite files, `app.database.bootstrap.create_database`
uses the ORM metadata directly. The initial migration remains revision `20260708_0001`;
the database has no external consumers yet, so this V1 baseline can still be refined
without introducing a V2 migration.

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

Build from the repository root, not from `backend/`, so Docker can copy both
the backend and the sibling CINDER package:

```bash
docker build -f backend/Dockerfile -t cvt-simulator-api .
docker run --rm -p 8000:8000 cvt-simulator-api
```

The container installs CINDER normally from the copied `cvtModel/` source. It
uses `requirements-runtime.txt`, which intentionally excludes the local
editable `-e ../cvtModel` dependency. This makes the deployed image independent
of the host checkout path while preserving the convenient local workflow.

The backend preset files are copied with `backend/`; for example, the tuned
launch preset is available at `/app/presets/baja-launch-baseline.json` inside
the image.

To confirm the image contains the expected preset:

```bash
docker run --rm cvt-simulator-api python -c "from pathlib import Path; print((Path('/app/presets') / 'baja-launch-baseline.json').is_file())"
```

## Black-box API testing

A manual end-to-end test plan is included in [`docs/BLACK_BOX_TESTING.md`](docs/BLACK_BOX_TESTING.md). It covers seeded library data, draft/release/fork/archive flows, library-resolved runs, direct-run comparison, cache reuse, preview artifacts, and full-result eviction/regeneration expectations.

For the automated version of the same flow, run:

```bash
PYTHONPATH=.:../cvtModel/src python -m app.scripts.smoke_library_database
```

## Main endpoints

```text
GET  /api/v1/health
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
GET/POST/PATCH /api/v1/library/tunes
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
```

Static studies return synchronously. Direct-contract simulations are
process-backed debug resources. Library-resolved runs are persisted in the
database and currently execute inline inside the request in V1 so the frozen
input contract, summaries, cache row, and full-result artifact can be verified
end-to-end before introducing a background DB worker. Product reruns should use
`POST /api/v1/runs/{run_id}/rerun`, which reuses the stored frozen input and
persists the regenerated output. All paths report only honest lifecycle states:
`queued`, `validating`, `running`, `completed`, `failed`, or `timed_out`; there
is no invented percent progress.

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
