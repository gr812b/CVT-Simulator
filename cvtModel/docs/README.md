# CINDER public-contract documentation

These notes describe the public boundary intended for a backend, a typed API,
and a frontend. CINDER remains mechanics-first: none of the modules in
`cinder.model` or `cinder.execution` know about HTTP, Pydantic, databases, or
UI state.

- [Getting started](GETTING_STARTED.md) — load, validate, decode, and run a full simulation document.
- [Public contract API](PUBLIC_CONTRACTS.md) — stable documents, validation findings, field schema, and result projections.
- [Document JSON Schema](DOCUMENT_SCHEMA.md) — generated-client source for the full v1 simulation document.
- [Lean contract cleanup](PHASE_1_1_CONTRACT_CLEANUP.md) — default payload shape, SI boundary rules, and editable-field exposure levels.
- [Apply Phase 1.1](../PHASE_1_1_APPLY.md) — verified patch/overlay application steps.
- [Backend / frontend handoff](BACKEND_FRONTEND_HANDOFF.md) — how an API should use CINDER without recreating CVT math.
- [Geometry study API](GEOMETRY_STUDY_API.md) — static geometry-design studies.
- [Actuation study API](ACTUATION_STUDY_API.md) — generic clamping-force response fields.
- [Platform refactor TODO](CVT_PLATFORM_REFACTOR_TODO.md) — tracked backend/frontend migration and future persistence plan.
