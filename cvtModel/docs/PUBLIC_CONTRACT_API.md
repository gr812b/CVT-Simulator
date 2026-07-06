# CINDER Public Contract API

This note describes the small, stable surface intended for a future backend,
CLI, saved-design workflow, or external Python caller. It does not replace the
mechanics APIs; it prevents those callers from depending on CINDER's internal
module layout.

## Conventions

```python
from cinder.contracts import public_conventions

conventions = public_conventions().as_dict()
```

CINDER uses SI values internally. The public conventions freeze:

- `R = r_secondary_effective / r_primary_effective`
- `R > 1` is a reduction ratio
- increasing global shift closes the primary, increases primary radius, and
  lowers ratio
- positive local clamping force closes the mounted pulley
- public numeric keys carry units where practical, such as
  `secondary_torque_Nm` and `total_clamping_force_N`

## Saved assembly designs

The versioned assembly document is deliberately CVT-only. Engine, vehicle,
road, solver, and scenario settings remain separate case/runtime choices.

```python
from cinder.contracts import encode_assembly_document, decode_assembly_document

payload = encode_assembly_document(assembly)
assembly = decode_assembly_document(payload)
```

The document supports CINDER's built-in components:

- axial spring
- centrifugal ramp using a piecewise ramp profile
- helical torque reaction using a helix profile
- linear and circular ramp segments

Unsupported custom Python force laws fail explicitly instead of being silently
misrepresented.

## Simulation-document JSON Schema

```python
from cinder.contracts import simulation_case_document_json_schema

schema = simulation_case_document_json_schema()
```

This standard JSON Schema describes the complete, canonical-SI, version-one
`cinder_simulation_case` document. API adapters can expose it directly and
frontend build tooling can generate a `SimulationCaseDocument` type from it.
It intentionally does not reflect CINDER internal dataclasses.

## Component catalog

```python
from cinder.contracts import component_catalog_document

catalog = component_catalog_document()
```

This returns factual component kinds, scalar inputs, units, descriptions, and
basic validity ranges. It is not a recommendation engine or frontend layout.

## Assembly preflight

```python
from cinder.contracts import validate_assembly

report = validate_assembly(assembly)
```

The report contains structured `severity`, `code`, `message`, and `location`
findings. Constructor-level physical invariants remain enforced by the model;
the preflight adds engineering-facing checks such as profile travel coverage,
helix coverage, compression-spring extension, zero friction, and optional wrap
thresholds.

## Static studies

Existing study APIs return native Python/NumPy data. Convert them to standard
JSON-ready columns only at the external boundary:

```python
from cinder.contracts import (
    project_clamping_force_response,
    project_geometry_path,
    project_radius_plane,
    project_ratio_sensitivity_field,
)
```

Each projection has this general shape:

```text
kind
shape
axis_keys
columns[]
  key
  label
  unit
  description
  values
```

The frontend can choose its own plot based on returned columns. CINDER does not
return chart instructions.

## Simulation result and metrics

```python
from cinder.contracts import summarize_simulation, project_simulation_result

metrics = summarize_simulation(result)
payload = project_simulation_result(result)
```

Metrics are derived from an already materialized result. They do not rerun the
simulation. Current standard values include duration, transitions, first
engagement, per-contact slip durations, speed/ratio extrema, traction
utilization extrema, and integrated work/slip-dissipation values when those
report channels were requested.

`project_simulation_result` includes one flattened `report_table`, self-describing
signals, exact transition records, metrics, warnings, and a JSON-safe final
state. Detailed `reported_segments` and the adaptive `raw_trace` are explicit
opt-ins for inspection/debugging; neither is included by default.

## Explicit boundary

CINDER owns:

```text
assembly construction and validation
static geometry and actuation studies
hybrid simulation
numeric results and standard projections
```

A backend owns:

```text
HTTP, jobs, cancellation, persistence, caches, access control,
frontend DTO choices, and plotting choices
```

The CINDER-only quickstart provides the same public-boundary smoke path:

```text
examples/quickstart.py
```

It exercises:

```text
assembly document -> decoded assembly -> validation -> geometry study
-> actuation study -> transient run -> JSON-safe response payload
```
