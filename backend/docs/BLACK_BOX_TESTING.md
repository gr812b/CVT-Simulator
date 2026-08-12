# Black-box API testing guide

This guide describes how to manually verify the database-backed CVT Simulator backend without reading or relying on internal implementation details. It is intended for testing the public API behavior after applying the CINDER inertia-boundary overlay and the backend database/run-preview overlay.

The goal is to prove that the user-facing flows work end to end:

1. seeded library data is available;
2. users can create, edit, release, fork, deprecate, and archive design objects;
3. a released vehicle assembly can be resolved into a frozen CINDER simulation case;
4. persisted runs can be rerun from their frozen stored input without re-resolving live objects;
5. run summaries, previews, frozen inputs, and full results can be retrieved;
6. full results can be treated as evictable while preview/stat/input data remain available;
7. stale/deprecated metadata affects selectors and warnings without breaking historical runs.

The legacy/direct `POST /runs` endpoint is a developer/debug endpoint. It may be
used for optional regression comparisons, but it is not required for black-box
product acceptance.

## Prerequisites

From the `backend/` directory, install dependencies and point the backend at CINDER:

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

For local SQLite testing:

```bash
rm -f cvt_simulator_dev.db
python -m app.scripts.init_database
uvicorn app.main:app --reload
```

For Postgres testing:

```bash
export CVT_DATABASE_URL='postgresql+psycopg://cvt:cvt@localhost:5432/cvt_simulator'
alembic upgrade head
python -m app.scripts.init_database
uvicorn app.main:app --reload
```

The API root is:

```text
http://localhost:8000/api/v1
```

Swagger UI is:

```text
http://localhost:8000/docs
```

## Useful shell setup

The examples below use `curl` and `jq`.

```bash
API=http://localhost:8000/api/v1
```

The current V1 backend uses deterministic demo seed data. It does not yet implement authentication, so account/user identifiers are supplied explicitly in request bodies where needed.

## Phase 1: service and metadata sanity

### 1. Health endpoint

```bash
curl -s "$API/health" | jq
```

Expected:

- HTTP 200;
- response indicates the service is healthy.

### 2. Metadata endpoints

```bash
curl -s "$API/metadata/conventions" | jq
curl -s "$API/metadata/catalog" | jq
curl -s "$API/metadata/editor-schema" | jq '. | type'
curl -s "$API/metadata/simulation-case-schema" | jq '. | type'
```

Expected:

- all return HTTP 200;
- schemas return JSON objects;
- no database setup error appears.

### 3. CORS preflight for PATCH

```bash
curl -i -X OPTIONS "$API/library/engines/some-id/draft" \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: PATCH'
```

Expected:

- successful preflight response;
- `PATCH` is allowed by CORS.

## Phase 2: seeded library visibility

### 1. Institutions

```bash
curl -s "$API/library/institutions" | jq
```

Expected:

- includes seeded Baja-oriented schools such as McMaster, Cornell, Virginia Tech, WVU, and RIT;
- no validation/verification is required in V1.

### 2. Public/default objects

```bash
curl -s "$API/library/engines?public_only=true" | jq
curl -s "$API/library/cvt-designs?public_only=true" | jq
curl -s "$API/library/output-systems?public_only=true" | jq
curl -s "$API/library/vehicle-assemblies?public_only=true" | jq
```

Expected:

- each list contains at least one seeded/default object;
- seeded examples are marked with catalog/default metadata;
- archived objects are not shown unless `include_archived=true` is used.

## Phase 3: mutable object lifecycle

This phase verifies draft, release, fork, explicit null, deprecate, and archive behavior.

### 1. Create an engine draft

```bash
ENGINE_BODY='{
  "account_id": "demo-account",
  "name": "Black-box test engine",
  "description": "Temporary engine for API testing",
  "visibility": "private",
  "draft_payload": {
    "kind": "full_throttle_torque_curve",
    "equivalent_rotational_inertia_kg_m2": 0.1,
    "points": [
      {"angular_speed_rad_per_s": 200.0, "torque_Nm": 24.0},
      {"angular_speed_rad_per_s": 300.0, "torque_Nm": 23.0}
    ],
    "low_speed_braking_torque_Nm": -5.0,
    "low_speed_braking_peak_speed_rad_per_s": 50.0,
    "high_speed_braking_torque_Nm": -20.0,
    "high_speed_braking_transition_width_rad_per_s": 150.0
  }
}'

curl -s -X POST "$API/library/engines" \
  -H 'Content-Type: application/json' \
  -d "$ENGINE_BODY" | tee /tmp/engine.json | jq

ENGINE_ID=$(jq -r '.id' /tmp/engine.json)
```

Expected:

- object is created;
- it has no released version yet;
- `draft_payload` is present.

### 2. Explicit null means clear, missing means preserve

```bash
curl -s -X PATCH "$API/library/engines/$ENGINE_ID/draft" \
  -H 'Content-Type: application/json' \
  -d '{"description": null, "source_url": null}' | jq
```

Expected:

- `description` is cleared to `null`;
- missing fields are preserved;
- this distinguishes explicit `null` from omitted keys.

### 3. Release the engine

```bash
curl -s -X POST "$API/library/engines/$ENGINE_ID/release" \
  -H 'Content-Type: application/json' \
  -d '{"release_notes": "black-box release"}' | tee /tmp/engine_version.json | jq

ENGINE_VERSION_ID=$(jq -r '.id' /tmp/engine_version.json)
```

Expected:

- a new immutable version is created;
- base engine `released_version_id` points at it;
- version has payload schema/validation metadata;
- version payload contains the input boundary and input inertia.

### 4. Fork a released engine

```bash
curl -s -X POST "$API/library/engines/versions/$ENGINE_VERSION_ID/fork" \
  -H 'Content-Type: application/json' \
  -d '{"account_id": "demo-account", "name": "Forked black-box engine"}' | tee /tmp/forked_engine.json | jq
```

Expected:

- new mutable engine object is created;
- `forked_from_version_id` points at the source version;
- draft payload is copied from the released source payload.

### 5. Deprecate a version

```bash
curl -s -X POST "$API/library/engines/versions/$ENGINE_VERSION_ID/deprecate" \
  -H 'Content-Type: application/json' \
  -d '{"validation_status": "deprecated", "message": "black-box stale version check"}' | jq
```

Expected:

- released version remains retrievable;
- validation/deprecation metadata is updated;
- future resolver calls may return warnings, not silently mutate old versions.

### 6. Archive an object

```bash
curl -s -X POST "$API/library/engines/$ENGINE_ID/archive" | jq
curl -s "$API/library/engines?include_archived=true" | jq
```

Expected:

- archived object is hidden from normal lists;
- it appears when `include_archived=true` is used;
- released versions and historical runs remain valid.

## Phase 4: CVT/output/assembly lifecycle sanity

Repeat the same fork/release path for seeded CVT and output-system objects. The important black-box checks are:

- a forked CVT can be released without nesting `cinder_assembly` inside `cinder_assembly`;
- the released CVT version preserves `tuning_schema`;
- output-system versions own `direct_secondary_shaft_inertia_kg_m2` and drivetrain/loss-model data;
- vehicle assembly versions pin released engine, CVT, and output-system versions.

Commands:

```bash
SEEDED_CVT_VERSION_ID=$(curl -s "$API/library/cvt-designs?public_only=true" | jq -r '.[0].released_version_id')
SEEDED_OUTPUT_VERSION_ID=$(curl -s "$API/library/output-systems?public_only=true" | jq -r '.[0].released_version_id')

curl -s -X POST "$API/library/cvt-designs/versions/$SEEDED_CVT_VERSION_ID/fork" \
  -H 'Content-Type: application/json' \
  -d '{"account_id": "demo-account", "name": "Forked black-box CVT"}' \
  | tee /tmp/forked_cvt.json | jq

FORKED_CVT_ID=$(jq -r '.id' /tmp/forked_cvt.json)

curl -s -X POST "$API/library/cvt-designs/$FORKED_CVT_ID/release" \
  -H 'Content-Type: application/json' \
  -d '{"release_notes": "release forked CVT"}' | jq

curl -s -X POST "$API/library/output-systems/versions/$SEEDED_OUTPUT_VERSION_ID/fork" \
  -H 'Content-Type: application/json' \
  -d '{"account_id": "demo-account", "name": "Forked black-box output"}' \
  | tee /tmp/forked_output.json | jq

FORKED_OUTPUT_ID=$(jq -r '.id' /tmp/forked_output.json)

curl -s -X POST "$API/library/output-systems/$FORKED_OUTPUT_ID/release" \
  -H 'Content-Type: application/json' \
  -d '{"release_notes": "release forked output"}' | jq
```

Expected:

- all requests return success;
- released CVT payload has a top-level CINDER assembly, not an accidental wrapper;
- released output payload contains output-boundary fields.

## Phase 5: tune, load case, and execution preset

```bash
curl -s "$API/library/tunes" | jq
curl -s "$API/library/load-cases" | jq
curl -s "$API/library/execution-presets" | jq
```

Expected:

- seeded tune/load-case/execution preset exists;
- they can be selected for a library run.

Optional null-clear check:

```bash
TUNE_ID=$(curl -s "$API/library/tunes" | jq -r '.[0].id')

curl -s -X PATCH "$API/library/tunes/$TUNE_ID" \
  -H 'Content-Type: application/json' \
  -d '{"notes": null}' | jq
```

Expected:

- notes are cleared rather than ignored.

## Phase 6: library-resolved run

Collect seeded IDs:

```bash
ASSEMBLY_VERSION_ID=$(curl -s "$API/library/vehicle-assemblies?public_only=true" | jq -r '.[0].released_version_id')
TUNE_ID=$(curl -s "$API/library/tunes" | jq -r '.[0].id')
LOAD_CASE_ID=$(curl -s "$API/library/load-cases" | jq -r '.[0].id')
EXECUTION_PRESET_ID=$(curl -s "$API/library/execution-presets" | jq -r '.[0].id')
```

Submit from library:

```bash
RUN_BODY=$(jq -n \
  --arg account_id "demo-account" \
  --arg user_id "demo-user" \
  --arg assembly_version_id "$ASSEMBLY_VERSION_ID" \
  --arg tune_id "$TUNE_ID" \
  --arg load_case_id "$LOAD_CASE_ID" \
  --arg execution_preset_id "$EXECUTION_PRESET_ID" \
  '{
    account_id: $account_id,
    created_by_user_id: $user_id,
    vehicle_assembly_version_id: $assembly_version_id,
    tune_id: $tune_id,
    load_case_id: $load_case_id,
    execution_preset_id: $execution_preset_id
  }')

curl -s -X POST "$API/runs/from-library" \
  -H 'Content-Type: application/json' \
  -d "$RUN_BODY" | tee /tmp/library_run.json | jq

RUN_ID=$(jq -r '.id' /tmp/library_run.json)
```

Expected:

- run completes successfully;
- response includes a run ID, status, contract hash, cache status, and summary data;
- run is listed in persisted library-run history.

```bash
curl -s "$API/runs" | jq
```

## Phase 7: retrieve stored run data

```bash
curl -s "$API/runs/$RUN_ID" | jq
curl -s "$API/runs/$RUN_ID/input" | tee /tmp/library_input.json | jq
curl -s "$API/runs/$RUN_ID/preview" | tee /tmp/library_preview.json | jq
curl -s "$API/runs/$RUN_ID/result" | tee /tmp/library_result.json | jq
```

Expected:

- `/input` returns the frozen full CINDER simulation case;
- `/preview` returns a versioned downsampled preview profile;
- `/result` returns the full simulation result while the full artifact exists;
- preview has fewer/equal points than the full report table and includes first/last points;
- summary stats are available even without opening the full result.

Preview fields expected in V1:

```text
time_s
state.primary_angular_speed
state.secondary_angular_speed
state.shift_position
kinematics.ratio
vehicle.speed
vehicle.distance
```

## Phase 8: persisted rerun from frozen input

Rerun the completed library run through the product rerun endpoint:

```bash
curl -s -X POST "$API/runs/$RUN_ID/rerun" \
  -H 'Content-Type: application/json' \
  -d '{}' | tee /tmp/stored_rerun.json | jq

RERUN_ID=$(jq -r '.id' /tmp/stored_rerun.json)

curl -s "$API/runs/$RERUN_ID/input" | tee /tmp/stored_rerun_input.json | jq
curl -s "$API/runs/$RERUN_ID/preview" | tee /tmp/stored_rerun_preview.json | jq
curl -s "$API/runs/$RERUN_ID/result" | tee /tmp/stored_rerun_result.json | jq
```

Expected:

- rerun response has `source = library`;
- status is `completed`;
- contract hash matches the original run;
- frozen input matches the original `/input` response's `input_document_snapshot`;
- full result is numerically equal to the original library result;
- preview is equal to the original preview;
- rerun appears in `GET /runs` persisted history.

This is the required user-facing rerun flow. It does not depend on the direct
full-contract debug endpoint.

### Optional developer regression check

If the direct debug endpoint is still enabled, you may also submit the frozen
input envelope to `POST /runs` and compare the direct result against the
library result. Treat this as a developer regression check only, not a product
acceptance requirement.

```bash
curl -s -X POST "$API/runs" \
  -H 'Content-Type: application/json' \
  --data-binary @/tmp/library_input.json | tee /tmp/direct_run.json | jq
```

## Phase 9: cache reuse

Submit the same library run again:

```bash
curl -s -X POST "$API/runs/from-library" \
  -H 'Content-Type: application/json' \
  -d "$RUN_BODY" | tee /tmp/library_run_cached.json | jq
```

Expected:

- response reports a cache hit;
- contract hash matches the first library run;
- cache entry ID matches or points to the same cached artifact lineage;
- preview and result are retrievable.

## Phase 10: evictable full result behavior

There is no public admin eviction endpoint in V1. The automated smoke test exercises full-result eviction internally by marking/removing the full-result artifact while verifying that:

- `Run.input_contract` remains available;
- `Run.summary_scalars` remains available;
- preview artifact remains available;
- full result can be regenerated with `POST /runs/{run_id}/rerun`;
- the rerun does not re-resolve live library objects.

For manual API testing, use this as an expected behavior checklist rather than a curl scenario unless an admin/debug eviction endpoint is added later.

## Phase 11: stale/deprecated behavior

After deprecating one pinned version, submit a run that still references it.

Expected:

- `deprecated` or `needs_migration` versions may produce resolver warnings;
- `invalid` or `unsupported` versions should be blocked;
- old runs already created from that version remain retrievable because they store frozen input contracts.

## Automated black-box smoke script

The strongest current end-to-end test is:

```bash
python -m app.scripts.smoke_library_database
```

It uses a temporary database and performs the main black-box flow programmatically:

- CORS PATCH preflight;
- seeded institution and catalog checks;
- engine/CVT/output/assembly lifecycle checks;
- explicit null-clear checks;
- deprecate/archive behavior;
- library run submission;
- persisted rerun from frozen input;
- full-result retrieval;
- preview retrieval and preview-vs-full sampled-value checks;
- cache-hit behavior;
- full-result eviction/regeneration behavior.

Run it before handing the backend to frontend/API testing.

## Pass/fail summary checklist

Use this as the final black-box acceptance checklist:

```text
[ ] health and metadata endpoints return 200
[ ] CORS permits PATCH preflight
[ ] institutions seed correctly
[ ] public/default engines, CVTs, output systems, and assemblies list correctly
[ ] draft update respects explicit null vs missing field
[ ] release creates immutable version
[ ] fork copies source payload and provenance
[ ] CVT fork/release preserves cinder_assembly and tuning_schema shape
[ ] output system owns gearbox/final-drive/direct secondary-shaft inertia
[ ] archive hides object from normal lists but include_archived reveals it
[ ] deprecate/supersede metadata is visible and does not mutate old runs
[ ] library run resolves and completes
[ ] frozen input is retrievable
[ ] full result is retrievable while artifact exists
[ ] preview is retrievable and downsampled/profile-versioned
[ ] summary stats are retrievable from run detail
[ ] persisted rerun from frozen input matches original library run output
[ ] repeated library run reuses cache
[ ] old input + preview survive full-result eviction behavior
[ ] POST /runs/{run_id}/rerun can regenerate full output
[ ] direct POST /runs comparison, if enabled, is treated as optional/dev-only
```
