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

## Tests and formatting

```bash
python -m pytest
flake8 app test
black --check app test
```
