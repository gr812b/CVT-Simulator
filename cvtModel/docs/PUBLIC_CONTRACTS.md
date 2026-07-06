# CINDER Phase-1 public contract

## Purpose and ownership

`cinder.contracts` is the stable external boundary over CINDER's mechanical
core. It owns:

- versioned documents;
- factual built-in component metadata;
- generic editable field descriptors;
- structured validation findings with document paths;
- JSON-safe study and result projections;
- standard simulation metrics.

It does **not** own HTTP routes, Pydantic models, user accounts, storage,
persistence, jobs, chart components, Three.js scene code, or UI layouts.

The dependency direction is one way:

```text
backend / frontend adapters -> cinder.contracts -> CINDER mechanics
```

Core CINDER modules never import `cinder.contracts`.

## Full simulation-case document

Document type: `cinder_simulation_case`.

```json
{
  "schema_version": 1,
  "document_type": "cinder_simulation_case",
  "assembly": { "document_type": "cinder_cvt_assembly" },
  "input_boundary": { "kind": "full_throttle_torque_curve" },
  "output_boundary": { "kind": "locked_final_drive_vehicle" },
  "scenario": { "time_span_s": [0, 3], "initial_state": {} },
  "execution": {
    "traction_law": {},
    "solve_settings": {},
    "operating_limits": {},
    "switching_settings": {},
    "integrator": {},
    "reporting": {}
  }
}
```

The exact complete shape is demonstrated by
`examples/baja_baseline_simulation_case.json`.

### Supported version-one boundary variants

| Area | Supported kind |
|---|---|
| Input boundary | `full_throttle_torque_curve` |
| Output boundary | `fixed_output_load`, `locked_final_drive_vehicle` |
| Road profile inside vehicle boundary | `constant_grade` |
| Reporting grid | `native`, `uniform_count`, `uniform_time_step` |

Custom Python boundaries and callable road profiles remain valid CINDER
extension points, but they are not silently serialized in v1. The encoder fails
clearly instead of creating a document that cannot be reproduced later.

## Decode and encode

```python
from cinder.contracts import (
    decode_simulation_case_document,
    encode_simulation_case_document,
)

# JSON document -> ordinary CINDER objects
decoded = decode_simulation_case_document(document)

# ordinary CINDER objects -> JSON-safe document
saved = encode_simulation_case_document(
    decoded.case,
    operating_system_config=decoded.operating_system_config,
    integrator_settings=decoded.integrator_settings,
    reporting_settings=decoded.reporting_settings,
)
```

The round trip protects the backend from CINDER constructor churn. Public
transport documents are explicit; they do not use reflection over private
mechanics types.

## Validation

```python
from cinder.contracts import validate_simulation_case_document

report = validate_simulation_case_document(document)
```

A finding includes both a stable CINDER location and a concrete JSON Pointer:

```json
{
  "severity": "warning",
  "code": "contact.zero_friction_coefficient",
  "location": "contact.friction_coefficient",
  "document_path": "/assembly/contact/friction_coefficient",
  "message": "The contact friction coefficient is zero, so traction capacity will be zero."
}
```

The frontend can highlight a document field/card by `document_path`; it does
not need a separate parameter-name mapping. Malformed documents return a single
`document.decode_error` finding at the root pointer (`""`) rather than forcing
an API route to catch and translate constructor exceptions.

## Editable-field schema

```python
from cinder.contracts import editable_simulation_case_schema
schema = editable_simulation_case_schema()
```

A field descriptor is intentionally generic:

```json
{
  "path_template": "/scenario/initial_state/shift_position_m",
  "label": "Shift position",
  "value_kind": "number",
  "dimension": "length",
  "canonical_unit": "m",
  "minimum": null,
  "required": true,
  "section": "Scenario",
  "exposure": "scenario"
}
```

A path template with `*` represents one array item. `supported_discriminators`
describes all built-in structural variants. The component catalog is included as
factual metadata, including supported mounts and component parameter types.

Each field also has one exposure level:

- `design` — CVT hardware and component design inputs;
- `scenario` — boundaries, road/load conditions, and initial conditions;
- `advanced_execution` — numerical/contact/reporting settings retained for
  reproducibility but normally hidden behind an advanced panel.

This is intentionally not a UI layout engine. The application controls tabs,
card order, copy, and visual treatment.

## Result projections

```python
from cinder.contracts import project_simulation_result
payload = project_simulation_result(result)
```

The result contains:

- `metrics`: standard cross-run scalar metrics;
- `summary`: terminal state and segment/transition counts;
- `report_table`: continuous time-aligned data for generic charts, playback, and 3D animation;
- `transitions`: exact event/transition markers;
- optional `reported_segments` when `include_reported_segments=True`;
- optional `raw_trace` when `include_raw_trace=True`.

The default projection deliberately contains one report surface only. It does
not duplicate the table under a legacy `segments` key.

`report_table.columns` are descriptors plus aligned value vectors. Missing
optional signals appear as `null`, not nonstandard JSON `NaN`. A segment
projection/reset can produce duplicate time values; this preserves the real
hybrid discontinuity rather than manufacturing a false interpolated state.

## Quantity descriptors

Every projected value has:

```text
key
label
canonical_unit
unit               (compatibility alias for canonical_unit)
dimension
description
```

The selected display unit is an application preference. Physical semantics and
canonical base-SI values remain CINDER-owned. CINDER may internally use
convenience representations such as degree-based ramp classes, but document and
projection boundaries emit radians, metres, and other base-SI values.

## JSON Schema export

CINDER exposes the public version-one simulation document as standard JSON
Schema. This is intended for API adapters and frontend build tooling; it does
not expose internal mechanics dataclasses.

```python
from cinder.contracts import simulation_case_document_json_schema

schema = simulation_case_document_json_schema()
```

The schema is canonical SI and describes the same `cinder_simulation_case`
document accepted by `decode_simulation_case_document(...)`.
