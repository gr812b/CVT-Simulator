# CINDER public document contracts

`cinder.contracts` is the stable versioned document boundary over CINDER's
mechanical core. It owns JSON-safe assembly/simulation documents, validation
findings, editable-field metadata, result projection, standard metrics, and
machine-readable JSON Schemas for the core simulation boundaries.

Core mechanics do not depend on the document layer.

## Public JSON Schemas

```python
from cinder.contracts import (
    assembly_document_json_schema,
    simulation_case_document_json_schema,
    simulation_result_json_schema,
)
```

These describe the CINDER-owned structure of the reusable CVT assembly, composed
simulation case, and projected simulation result respectively. The composed case
keeps host and shaft-boundary payload contents opaque because those are extension
slots rather than fixed CINDER-core implementations.

## Composed simulation-case document

Document type:

```text
cinder_composed_simulation_case
```

A version-one document contains:

```text
assembly          physical CVT hardware
shaft_boundaries  primary and secondary external boundary slots
host              composed-system host slot
scenario          time span and five-state CVT initial condition
execution         integrator and reporting settings
```

The complete current shape is demonstrated by
`examples/baja_baseline_simulation_case.json`.

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

The composed simulation adds external context and execution configuration:

```text
shaft-boundary slots
host slot
initial conditions
time span
integrator settings
reporting settings
```

All public numeric values are SI.

## Simulation-result fields

Simulation-case documents and simulation-result projections are versioned
independently. The current simulation-case schema remains version 1, while
`project_simulation_result(result)` emits simulation-result contract version 2.
The result contract covers both scalar report data and compact spatial results.
In addition to `report_table`, a projected result can contain:

```text
domains   reusable spatial domains and their geometry expressions
fields    scalar derived fields attached to those domains
```

The initial built-ins are:

```text
belt.path       planar closed effective-radius belt path
belt.tension    continuous reduced-model belt tension on belt.path
```

Expressions are JSON-safe trees. Their leaves are literals, the local region
coordinate `u`, or references to existing report-table signal keys. Operators
are ordinary generic math (`add`, `sub`, `mul`, `div`, `neg`, `abs`, `exp`,
`expm1`, `sin`, `cos`, `sqrt`, `lt`, and `where`). A consumer therefore needs
only one generic expression evaluator rather than field-specific CVT equations.

For belt tension, four additional ordinary report columns are emitted when
contact reporting is enabled:

```text
contact.primary_tension_in
contact.primary_tension_out
contact.secondary_tension_in
contact.secondary_tension_out
```

The field definition is transmitted once and references these columns together
with existing geometry/contact signals.
