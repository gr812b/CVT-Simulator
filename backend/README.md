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

## Run locally

From `backend/`:

```bash
python -m venv venv
venv\Scripts\activate             # Mac: source venv/bin/activate    
python -m pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

The API is served at `http://localhost:8000/api/v1`; Swagger UI is at
`http://localhost:8000/docs`.

## Main endpoints

```text
GET  /api/v1/health
GET  /api/v1/metadata/conventions
GET  /api/v1/metadata/catalog
GET  /api/v1/metadata/editor-schema
GET  /api/v1/metadata/simulation-case-schema
GET  /api/v1/presets
GET  /api/v1/presets/{preset_id}
POST /api/v1/simulation-cases/validate
POST /api/v1/studies/geometry/endpoint-radii
POST /api/v1/studies/geometry/target-ratios
POST /api/v1/studies/actuation/clamping-response
POST /api/v1/runs
GET  /api/v1/runs/{run_id}
GET  /api/v1/runs/{run_id}/result
```

Static studies return synchronously. Simulations are process-backed run
resources. They report only honest lifecycle states: `queued`, `validating`,
`running`, `completed`, `failed`, or `timed_out`; there is no invented percent
progress.

## Type generation

```bash
python -m app.scripts.export_contract_artifacts --output-dir generated
```

This writes:

- `generated/openapi.json` for endpoint/request/response TypeScript types;
- `generated/cinder_simulation_case.schema.json` for the canonical nested
  `SimulationCaseDocument` TypeScript type.

Use generated types in the frontend; do not create a parallel parameter map.

## Tests

```bash
python -m pytest
flake8 app test
black --check app test
```
