# Public contract API

The public contract serializes the composed simulation boundary, not the old
primary/secondary composed-system document.

A simulation document contains:

```text
assembly          CVT-only hardware document
shaft_boundaries  primary and secondary shaft-port definitions
host              host type and initial host state
scenario          time span and five-state CVT initial condition
execution         integrator and reporting preferences
```

The current built-in shaft boundaries supported by the document adapter are:

- `fixed_shaft`
- `full_throttle_engine`
- `locked_final_drive`

The normal Python route is:

```python
from cinder.contracts import decode_simulation_case_document

decoded = decode_simulation_case_document(document)
result = decoded.system.run(
    time_span=decoded.time_span,
    initial_state=decoded.initial_state,
    initial_mode=decoded.initial_mode,
    settings=decoded.integrator_settings,
    reporting_settings=decoded.reporting_settings,
)
```

The schema is available through:

```python
from cinder.contracts import simulation_case_document_json_schema
schema = simulation_case_document_json_schema()
```

All public numeric values are SI.
