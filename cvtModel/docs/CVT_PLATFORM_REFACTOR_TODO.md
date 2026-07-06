# CVT Platform Refactor TODO

## Purpose

Rebuild the backend and frontend around CINDER's public contracts so that CVT mechanics, geometry, simulation, validation, and study calculations live in one place: CINDER.

The application layer should transport versioned documents to CINDER, store and present CINDER's results, and provide user-facing workflows. It must not reimplement CVT math, parameter translation, result reconstruction, or unit-specific CVT logic.

---

## Architecture decisions to keep

- **CINDER owns mechanics and canonical SI values.** It remains independent of HTTP, databases, users, authentication, persistence, and UI concerns.
- **The backend owns API transport, jobs, persistence, presets, access control, and presentation manifests.** It imports CINDER only through its public contract APIs.
- **The frontend owns editing experience, layout, selected display units, charts, 3D rendering, and navigation.** It never reproduces CVT calculations.
- **Saved/run documents are self-contained snapshots.** A CINDER run must never depend on a mutable database row remaining unchanged.
- **Public API types are explicit backend DTOs.** Generate TypeScript from FastAPI/OpenAPI; do not reflect CINDER internals into Pydantic automatically.
- **CINDER's internal types remain free to evolve.** Only its documented contracts are API-facing.

---

# A. Current refactor work

## A1. Complete CINDER's external contract

### A1.1 Add a full simulation-case document

- [ ] Define a versioned `SimulationCaseDocument` in CINDER.
- [ ] Include:
  - [ ] `assembly`
  - [ ] `input_boundary`
  - [ ] `output_boundary`
  - [ ] `scenario`
  - [ ] `initial_state`
  - [ ] `execution`
- [ ] Provide `decode_simulation_case_document(...)`.
- [ ] Provide `encode_simulation_case_document(...)`.
- [ ] Keep the document in canonical SI units.
- [ ] Make construction use the ordinary CINDER constructors, not a parallel backend-only model.
- [ ] Add round-trip and migration tests.

**Done when:** a complete launch or dyno case can be encoded, decoded, validated, and run without the backend constructing model objects manually.

### A1.2 Add editable-field descriptors

- [ ] Define stable descriptors for fields that a user may edit.
- [ ] Each descriptor should contain:
  - [ ] stable document path (JSON Pointer preferred)
  - [ ] label and short description
  - [ ] value type (`number`, `integer`, `boolean`, `string`, discriminated object, list)
  - [ ] physical dimension
  - [ ] canonical unit
  - [ ] required/optional status
  - [ ] default, where a default exists
  - [ ] static lower/upper bounds where physically meaningful
  - [ ] enum choices or permitted component kinds where applicable
- [ ] Keep descriptors factual and mechanical. Do not put frontend layout, colour, icon, or marketing copy in CINDER.
- [ ] Support context-sensitive descriptors where a selected component kind changes its editable fields.

**Done when:** the frontend can build generic quantity editors and structural component editors without a hand-maintained parameter registry.

### A1.3 Make validation target documents directly

- [ ] Ensure every validation finding has a stable code, severity, message, and JSON Pointer `document_path` when applicable.
- [ ] Distinguish hard invalidity from warnings and informational findings.
- [ ] Validate complete simulation-case documents as well as assembly-only documents.
- [ ] Keep validation pure and side-effect free.

**Done when:** a frontend can highlight the relevant editor/card by matching one returned document path.

### A1.4 Standardize result projections

- [ ] Retain raw segments/traces for inspection and debugging.
- [ ] Add a single continuous `report_table` for normal charts and 3D playback.
- [ ] Include self-describing axes/columns with key, label, dimension, canonical unit, and values.
- [ ] Include transition markers and summary metrics with the report.
- [ ] Project geometry and actuation study results through the same field/axis conventions.

**Done when:** a consumer can draw a chart from a result table without stitching hybrid segments or inventing CVT-specific property maps.

### A1.5 Freeze and document public conventions

- [ ] Ratio definition and direction.
- [ ] Shift-coordinate direction and limits.
- [ ] Force and torque sign conventions.
- [ ] Canonical SI units and public field naming rules.
- [ ] Required/optional semantics for all public documents.
- [ ] Public entry points and result types.

---

# B. Backend refactor

## B1. Replace the monolithic endpoint module

- [ ] Create versioned routing under `app/api/v1/`.
- [ ] Split routes by user-facing capability:
  - [ ] `metadata.py`
  - [ ] `presets.py`
  - [ ] `designs.py`
  - [ ] `studies.py`
  - [ ] `runs.py`
- [ ] Keep routes thin: parse DTO -> call service -> return DTO.
- [ ] Move CINDER calls behind a focused service/gateway layer.
- [ ] Do not import CINDER internals in route files.

Suggested shape:

```text
app/
  api/v1/
    router.py
    metadata.py
    presets.py
    designs.py
    studies.py
    runs.py
  schemas/
    common.py
    metadata.py
    designs.py
    studies.py
    runs.py
  services/
    cinder_gateway.py
    design_service.py
    study_service.py
    run_service.py
    result_view_service.py
  jobs/
    runner.py
    store.py
  presentation/
    unit_profiles.py
    result_views.py
  presets/
    baja_launch_baseline.json
```

## B2. Remove auto-generated reflection models

- [ ] Delete the internal-class reflection path (`auto_model.py`) after its replacements exist.
- [ ] Define explicit Pydantic DTOs for public API requests/responses.
- [ ] Keep DTOs thin and structurally close to CINDER's public documents/projections.
- [ ] Add contract tests:
  - [ ] request DTO -> JSON-safe document
  - [ ] CINDER decode/validate/run/study
  - [ ] CINDER projection -> response DTO
- [ ] Generate TypeScript from OpenAPI.

**Rule:** backend types describe the public API, not arbitrary CINDER implementation objects.

## B3. Establish named study endpoints

- [ ] `GET /api/v1/metadata/conventions`
- [ ] `GET /api/v1/metadata/catalog`
- [ ] `GET /api/v1/presets`
- [ ] `POST /api/v1/designs/validate`
- [ ] `POST /api/v1/studies/geometry/endpoint-radii`
- [ ] `POST /api/v1/studies/geometry/target-ratios`
- [ ] `POST /api/v1/studies/actuation/clamping-force`
- [ ] Reserve future study namespaces for traction, equilibrium, losses, and sweeps.

Do not expose endpoints named after internal solvers.

## B4. Introduce a run resource for simulations

- [ ] `POST /api/v1/runs` creates a run from a full simulation-case document snapshot.
- [ ] `GET /api/v1/runs/{run_id}` returns status, progress, and result when complete.
- [ ] `GET /api/v1/runs/{run_id}/events` provides SSE progress/events when needed.
- [ ] Define run states: `queued`, `running`, `completed`, `failed`, `cancelled`.
- [ ] The worker receives an immutable input snapshot.
- [ ] Result projection happens once after completion and is stored/cached by the application layer.
- [ ] Keep an in-memory run store initially; do not couple the API shape to it.

## B5. Use presentation manifests for charts, not frontend graph registries

- [ ] Backend returns result values from CINDER.
- [ ] Backend owns named view manifests, e.g. `launch_results`.
- [ ] A manifest selects report-table columns, groups plots into sections, and requests generic overlays.
- [ ] Support generic overlays:
  - [ ] horizontal scalar reference
  - [ ] vertical event marker
  - [ ] shaded operating range
  - [ ] threshold/limit line
- [ ] Frontend owns one generic chart renderer.

**Rule:** CINDER returns facts; backend decides which facts comprise a product view; frontend renders the view.

## B6. Unit handling without CVT-specific conversion maps

- [ ] Documents, API values, CINDER values, and 3D geometry remain canonical SI.
- [ ] Return dimension/unit metadata with editable fields and result columns.
- [ ] Frontend has one generic unit conversion/formatting layer keyed by physical dimension.
- [ ] Start with one fixed Baja display profile:
  - [ ] length: mm
  - [ ] angular speed: RPM
  - [ ] vehicle speed: km/h
  - [ ] force: N
  - [ ] torque: N m
  - [ ] mass: kg
  - [ ] angle: degrees
- [ ] Keep the selected display profile outside saved CINDER documents.

**Rule:** frontend conversion code knows dimensions and units, never parameter names such as `flyweight_mass` or `shift_position`.

## B7. 3D rendering boundary

- [ ] Drive the scene only from resolved geometry/report signals returned by CINDER.
- [ ] Keep only render adaptation in the frontend: metres-to-scene scale and model-axis mapping.
- [ ] Remove geometry reconstruction from the scene layer.

---

# C. Frontend migration

## C1. Document-first state

- [ ] Store a full `SimulationCaseDocument` as the editable design draft.
- [ ] Apply edits directly to the document shape.
- [ ] Stop translating PascalCase/camelCase/snake_case parameter maps.
- [ ] Preserve an optional UI-only source/provenance record separately from the document.

## C2. Generic design editors

- [ ] Use catalog/descriptors to populate supported component choices.
- [ ] Render generic quantity controls from field descriptors.
- [ ] Build bespoke controls only for genuinely structural structures:
  - [ ] piecewise ramp profiles
  - [ ] engine curve editor
  - [ ] helix profile editor if/when needed
  - [ ] belt selector
- [ ] Call validation after meaningful edits with debouncing.
- [ ] Map returned findings to the relevant document paths.

## C3. First vertical slice

- [ ] Select a preset.
- [ ] Edit its CVT assembly.
- [ ] Validate it.
- [ ] View geometry study.
- [ ] View actuator clamping study.
- [ ] Use the returned columns/metadata to render plots.

**Done when:** a user can create a useful static design workspace without legacy parameter or graph utilities.

## C4. Simulation result route

- [ ] Create a run.
- [ ] Show job status/progress.
- [ ] Render summary metrics.
- [ ] Render backend-selected view manifests from the report table.
- [ ] Animate 3D geometry from report values.
- [ ] Show transition/event markers.

## C5. Delete legacy frontend plumbing after each migrated route

- [ ] manual parameter mappings
- [ ] nested response conversion functions
- [ ] graph accessor/category registries
- [ ] handwritten result-to-scene geometry calculations
- [ ] legacy `/run`, `/solvers`, `/constants` client paths

---

# D. Future persistence, accounts, libraries, and saved runs

## D1. Principle: CINDER remains unchanged

CINDER should not know that a design belongs to a user, database row, workspace, organization, preset library, or saved run. It only receives/resolves a complete versioned document and returns results.

Persistence belongs entirely to the backend/application layer.

## D2. Future domain objects

Plan around these concepts, but do not implement their database tables yet.

### User and preferences

```text
User
  id
  identity/authentication data
  created/updated timestamps

UserPreferences
  user_id
  display-unit profile
  preferred theme / UI preferences
  future default report preferences
```

Preferences must never change the canonical values stored in CINDER documents or run snapshots.

### Library items

A reusable engine, belt, full CVT design, or future component preset should be represented as a library item with a discriminated kind:

```text
LibraryItem
  id
  kind: engine | belt | cvt_design | component_preset
  visibility: built_in | private | shared | public
  owner/principal reference (nullable for built-ins)
  name, description, tags
  current_revision_id
  provenance/source information
```

Each revision stores a versioned JSON document appropriate to its kind:

```text
LibraryItemRevision
  id
  library_item_id
  revision_number
  document_schema_kind
  document_schema_version
  document_json
  content_hash
  created_at
```

This avoids a prematurely rigid relational schema for every future actuator/belt/engine subtype while retaining explicit `kind` values and document validation.

### Saved CVT designs

A full editable user CVT configuration should be a named design with immutable revisions:

```text
Design
  id
  owner/principal reference
  name
  current_revision_id
  visibility

DesignRevision
  id
  design_id
  revision_number
  simulation_case_document_json
  CINDER document schema version
  content_hash
  created_at
```

A design revision is the reproducible input for a run.

### Simulation runs

```text
SimulationRun
  id
  submitted_by / owner
  optional design_revision_id
  status
  submitted_at / started_at / completed_at
  input_snapshot_json
  CINDER package version
  document schema version
  numerical environment metadata
  summary_metrics_json
  result_artifact_manifest_json
  error summary, if failed
```

A run may link to a design revision, but it must always store its own complete immutable input snapshot.

That protects reproducibility when a saved design, belt, or engine later changes or is deleted.

## D3. Library references versus resolved documents

The editor may show that a design uses a saved belt or engine:

```text
selected source: belt library item B / revision 4
```

But before validation, simulation, or persistence of a run, the backend resolves it into a complete embedded CINDER document.

Persist both when useful:

```text
resolved simulation-case document
+ provenance metadata that says where the belt/engine originally came from
```

Do **not** make a run depend solely on foreign-key references to mutable library rows.

## D4. Storage strategy when persistence begins

Recommended split:

- **Relational database**: users, preferences, ownership, library metadata, design revisions, run rows, status, hashes, summaries, permissions, artifact pointers.
- **Object/blob storage**: large report tables, raw traces, dense histories, archived result exports, generated figures if retained.
- **JSON documents**: versioned CINDER design/case documents and small result projections. A JSON-capable relational column is a good fit later.

Likely progression:

```text
now: in-memory run store + version-controlled built-in JSON presets
later local/dev: SQLite or local object files if useful
production/multi-user: PostgreSQL + object storage
```

Do not store every potentially large simulation array in a normal relational row by default.

## D5. Authentication and access control later

Do not add auth now. Make it easy to add without changing CINDER:

- Route dependencies resolve the current actor/user.
- Services accept an actor/principal where ownership checks matter.
- CINDER gateway and solver calls never receive an actor.
- Start with one owner field; introduce teams/workspaces only if collaboration becomes real.

Avoid designing a speculative organization/role system now.

## D6. Versioning and migrations

There are two separate migration systems:

1. **CINDER document migrations**: convert older public document versions into currently supported CINDER documents.
2. **Database migrations**: evolve application tables and indexes.

Persist both the document schema version and the CINDER package/build version with each revision and run.

Do not silently rewrite old saved designs. Offer an explicit migration that creates a new revision once persistence exists.

## D7. Safe seams to create now; things to defer

### Create now

- [ ] Public, self-contained versioned CINDER documents.
- [ ] Stable opaque identifiers in backend responses (`UUID` or `ULID` style; choose one later).
- [ ] `PresetProvider` abstraction backed by JSON files.
- [ ] `RunStore` abstraction backed by memory.
- [ ] `RunService` and `DesignService` boundaries separate from FastAPI routes.
- [ ] Immutable run input snapshots.
- [ ] Metadata fields for schema/CINDER/numerical environment versions.
- [ ] Explicit API DTOs and OpenAPI type generation.

### Defer deliberately

- [ ] Database and ORM selection.
- [ ] Authentication provider.
- [ ] User tables and authorization policies.
- [ ] Background queue infrastructure.
- [ ] Object storage vendor.
- [ ] Collaborative editing.
- [ ] Sharing/public gallery workflows.
- [ ] Database schema for every individual actuator subtype.

---

# E. Recommended delivery sequence

## Phase 1 — CINDER contract completion

- [ ] A1.1 through A1.5.
- [ ] Contract round-trip, migration, and projection tests.

## Phase 2 — backend static-design API

- [ ] B1 through B3.
- [ ] Static JSON presets through `PresetProvider`.
- [ ] Stateless document validation.
- [ ] Geometry and actuation study endpoints.
- [ ] OpenAPI generation and typed frontend client.

## Phase 3 — frontend static design workspace

- [ ] C1 through C3.
- [ ] Delete old parameter mapping and static-study graph utilities as the new route replaces them.

## Phase 4 — simulation jobs and results

- [ ] B4 through B7 and C4.
- [ ] In-memory `RunStore` first.
- [ ] Result-view manifests and generic charts.
- [ ] 3D playback driven only from CINDER report signals.

## Phase 5 — persistence and accounts, only when valuable

- [ ] Convert file presets / in-memory run store to persistent implementations.
- [ ] Add saved designs, immutable revisions, users, and preferences.
- [ ] Move large results to artifact storage.
- [ ] Add sharing/visibility only after a real user need exists.

---

# Success criteria

The refactor is successful when:

- A single versioned document can be edited, validated, studied, simulated, saved later, and reproduced later.
- CINDER remains unaware of HTTP, users, databases, jobs, and frontend display preferences.
- The frontend has no CVT-specific unit conversion or parameter-name mapping utilities.
- The frontend can render most fields/charts from descriptors and tables rather than handwritten property accessors.
- A backend route can be changed without changing CINDER internals, and CINDER internals can evolve without breaking public API contracts.
- A future saved run preserves exactly what was simulated, including resolved belt/engine/CVT input and numerical environment metadata.
