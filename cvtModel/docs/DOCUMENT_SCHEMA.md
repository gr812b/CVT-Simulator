# CINDER public JSON Schemas

CINDER exposes JSON Schema for the three core serialized simulation boundaries:

```python
from cinder.contracts import (
    assembly_document_json_schema,
    simulation_case_document_json_schema,
    simulation_result_json_schema,
)

assembly_schema = assembly_document_json_schema()
case_schema = simulation_case_document_json_schema()
result_schema = simulation_result_json_schema()
```

The schemas describe CINDER-owned public JSON structure, discriminators, and
basic scalar bounds without exposing internal mechanics dataclasses.

## Ownership boundary

The assembly schema is complete for CINDER's serializable CVT hardware document.
The simulation-case schema composes that assembly with CINDER-owned CVT state,
integrator settings, and reporting settings.

Composed-system host and shaft-boundary payloads are intentional extension
slots. Their implementation-specific contents are therefore left opaque in the
core CINDER schema rather than freezing example host or boundary implementations
into CINDER's type contract.

The simulation-result schema describes `project_simulation_result(...)`,
including report tables, transitions, metrics, compact spatial domains, spatial
fields, and the generic field-expression AST.

Useful consumers include:

- non-Python clients;
- JSON editors and configuration tools;
- generated client types;
- saved-case/result validation at integration boundaries.

Decode/validation remains authoritative for engineering checks:

```python
from cinder.contracts import (
    decode_simulation_case_document,
    validate_simulation_case_document,
)
```

CINDER validation can reject mechanics-specific invalidity that structural JSON
Schema alone cannot establish, such as incompatible pulley geometry or invalid
mechanism travel.

All canonical physical values are SI.
