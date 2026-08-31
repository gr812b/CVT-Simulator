# CINDER simulation-document JSON Schema

CINDER exposes the version-one `cinder_composed_simulation_case` document as
standard JSON Schema:

```python
from cinder.contracts import simulation_case_document_json_schema

schema = simulation_case_document_json_schema()
```

The schema describes the public JSON shape, discriminators, and basic scalar
bounds. It deliberately does not expose internal mechanics dataclasses.

Useful consumers include:

- non-Python clients;
- JSON editors and configuration tools;
- generated client types;
- saved-case validation before decode.

Decode/validation remains authoritative for engineering checks:

```python
from cinder.contracts import (
    decode_simulation_case_document,
    validate_simulation_case_document,
)
```

CINDER validation can reject mechanics-specific invalidity that a structural
JSON Schema alone cannot establish, such as incompatible pulley geometry or
invalid mechanism travel.

All canonical document values are SI.
