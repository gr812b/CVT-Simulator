# CINDER public contract

## Purpose and ownership

`cinder.contracts` is the stable document boundary over the CINDER mechanical core. It owns versioned JSON-safe documents, validation findings, editable-field descriptors, result projections, and standard simulation metrics.

The dependency direction is one way:

```text
backend / frontend adapters -> cinder.contracts -> CINDER mechanics
```

Core CINDER modules do not import `cinder.contracts`.

## Composed simulation-case document

Document type: `cinder_composed_simulation_case`.

```json
{
  "schema_version": 1,
  "document_type": "cinder_composed_simulation_case",
  "assembly": { "document_type": "cinder_cvt_assembly" },
  "shaft_boundaries": {
    "primary": { "kind": "full_throttle_engine" },
    "secondary": { "kind": "locked_final_drive" }
  },
  "host": { "kind": "secondary_shaft_angle" },
  "scenario": {
    "time_span_s": [0.0, 5.0],
    "initial_cvt_state": {},
    "initial_host_state": {}
  },
  "execution": {
    "integrator": {},
    "reporting": {}
  }
}
```

The complete version-one shape is demonstrated by `examples/baja_baseline_simulation_case.json`.

## Supported built-ins

| Area | Supported kind |
|---|---|
| Primary shaft boundary | `fixed_torque`, `full_throttle_engine` |
| Secondary shaft boundary | `fixed_torque`, `locked_final_drive` |
| Host | `secondary_shaft_angle` |
| Road profile | `constant_grade`, `piecewise_constant_grade` |
| Reporting grid | `native`, `uniform_count`, `uniform_time_step` |

Custom Python shaft boundaries and hosts remain normal CINDER extension points. The JSON document encoder only serializes built-ins it can reproduce later; unsupported objects fail clearly.

## Decode and encode

```python
from cinder.contracts import (
    decode_simulation_case_document,
    encode_simulation_case_document,
)

decoded = decode_simulation_case_document(document)

saved = encode_simulation_case_document(
    assembly=decoded.assembly,
    primary_boundary=decoded.system.primary_boundary,
    secondary_boundary=decoded.system.secondary_boundary,
    host=decoded.system.host,
    initial_cvt_state=decoded.initial_cvt_state,
    initial_host_state=decoded.initial_host_state,
    time_span=decoded.time_span,
    integrator_settings=decoded.integrator_settings,
    reporting_settings=decoded.reporting_settings,
)
```

## Validation

```python
from cinder.contracts import validate_simulation_case_document

report = validate_simulation_case_document(document)
```

A validation finding contains a stable CINDER location and a JSON Pointer:

```json
{
  "severity": "warning",
  "code": "contact.zero_friction_coefficient",
  "location": "contact.static_friction_coefficient",
  "document_path": "/assembly/contact/static_friction_coefficient",
  "message": "The static friction coefficient is zero, so traction capacity will be zero."
}
```

The frontend can highlight a field by `document_path` without knowing CINDER constructor names.

## Editable-field schema

```python
from cinder.contracts import editable_simulation_case_schema

schema = editable_simulation_case_schema()
```

Editable fields are JSON Pointer templates over the composed simulation document. Fields marked with `*` apply to array items, such as torque-curve points or road-profile segments.

## Physical ownership rules

The serialized assembly owns physical CVT hardware:

```text
geometry
inertias
contact friction coefficients
primary pulley hardware
secondary pulley hardware
actuators
helical couplers
```

The composed simulation owns external shaft boundaries and host state:

```text
primary shaft boundary
secondary shaft boundary
host state
initial conditions
time span
integrator/report sampling
```

Shift stops and clutch/dead-zone limits are not serialized as execution settings. They are derived from CVT geometry:

```text
lower stop        -> shift = 0
engagement shift  -> geometry.deadzone_shift
upper stop        -> geometry.max_shift
```

The contact traction implementation is also not serialized as a user-selectable execution object. The solver derives the internal contact law from `BeltContactSpec` friction coefficients.
