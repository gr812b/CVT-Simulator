# CINDER public simulation-document JSON Schema

CINDER exposes the complete version-one `cinder_simulation_case` document as
standard JSON Schema:

```python
from cinder.contracts import simulation_case_document_json_schema

schema = simulation_case_document_json_schema()
```

The schema is an adapter over CINDER's stable public document contract. It does
not inspect or expose mechanics dataclasses. It is suitable for:

- frontend TypeScript generation;
- non-Python API clients;
- JSON-editor tooling;
- contract snapshots in CI.

The canonical document remains SI-only. Decode/validation remains authoritative
for constructor-level and engineering validation:

```python
from cinder.contracts import (
    decode_simulation_case_document,
    validate_simulation_case_document,
)
```

The schema describes JSON shape, supported discriminators, and basic scalar
bounds. CINDER validation still detects mechanics-specific invalidity such as
incompatible geometry, incomplete ramp/helix travel, and operating-limit
inconsistency.
