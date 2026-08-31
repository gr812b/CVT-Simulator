# CINDER public document contracts

`cinder.contracts` is the stable versioned document boundary over CINDER's
mechanical core. It owns JSON-safe assembly/simulation documents, validation
findings, editable-field metadata, result projection, and standard metrics.

Core mechanics do not depend on the document layer.

## Composed simulation-case document

Document type:

```text
cinder_composed_simulation_case
```

A version-one document contains:

```text
assembly          physical CVT hardware
shaft_boundaries  primary and secondary external boundary definitions
host              non-CVT state required by those boundaries
scenario          time span and five-state CVT initial condition
execution         integrator and reporting settings
```

The complete current shape is demonstrated by
`examples/baja_baseline_simulation_case.json`.

## Supported serialized built-ins

| Area | Supported kind |
|---|---|
| Shaft boundary | `fixed_shaft` |
| Primary shaft boundary | `full_throttle_engine` |
| Secondary shaft boundary | `locked_final_drive` |
| Host | `secondary_shaft_angle` |
| Road profile | `constant_grade`, `piecewise_constant_grade` |
| Reporting grid | `native`, `uniform_count`, `uniform_time_step` |

Custom Python shaft boundaries, hosts, and force laws remain normal Python
extension points. The JSON encoder serializes only built-ins it can reproduce
unambiguously.

## Decode and validate

```python
from cinder.contracts import (
    decode_simulation_case_document,
    validate_simulation_case_document,
)

report = validate_simulation_case_document(document)
if not report.is_valid:
    raise ValueError(report.findings)

decoded = decode_simulation_case_document(document)
```

The decoded case exposes its system, time span, initial state/mode, integrator
settings, and reporting settings.

## Run a decoded case

```python
result = decoded.system.run(
    time_span=decoded.time_span,
    initial_state=decoded.initial_state,
    initial_mode=decoded.initial_mode,
    settings=decoded.integrator_settings,
    reporting_settings=decoded.reporting_settings,
)
```

## Encode a reproducible case

```python
from cinder.contracts import encode_simulation_case_document

saved = encode_simulation_case_document(
    assembly=assembly,
    primary_boundary=primary_boundary,
    secondary_boundary=secondary_boundary,
    host=host,
    initial_cvt_state=initial_cvt_state,
    initial_host_state=initial_host_state,
    time_span=time_span,
    integrator_settings=integrator_settings,
    reporting_settings=reporting_settings,
)
```

## Physical ownership

The assembly owns CVT hardware:

```text
geometry
inertias
belt contact coefficients
primary and secondary actuator components
helical couplings
```

The composed simulation owns external context:

```text
shaft boundaries
host state
initial conditions
time span
integrator settings
reporting settings
```

Shift stops and dead-zone limits are derived from geometry rather than repeated
as execution parameters.

All public numeric values are SI.
