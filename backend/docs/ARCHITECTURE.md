# Phase-2 backend architecture

## Ownership

- **CINDER** owns CVT documents, decoding, validation, simulations, studies,
  metrics, and SI projections.
- **Backend** owns HTTP, Pydantic envelopes, preset/run storage, worker process
  lifecycle, and API error boundaries.
- **Frontend** owns document editing, display units, chart selection/styling,
  and 3D presentation.

The backend intentionally contains no graph manifest, unit conversion registry,
CVT calculation, or parameter-alias mapping.

## Persistence seam

`PresetStore` and `RunStore` are protocols. Phase 2 supplies `JsonPresetStore`
and `InMemoryRunStore`; a database can later replace only those implementations.
Every run retains an immutable `input_document_snapshot` and SHA-256 fingerprint
alongside the result/error snapshot, so saved runs remain reproducible even when
a user later edits a CVT, engine, or belt design.

## Worker model

The production default is a spawned local process. The parent can kill it after
`CVT_RUN_TIMEOUT_SECONDS` (default `120`). Tests select the inline executor.
No continuous progress is fabricated because CINDER does not expose meaningful
integrator progress yet.


## CINDER package and result-contract boundary

The backend depends on an immutable PyPI release of `cinder-cvt`, pinned in
`requirements.txt`. `app/application/cinder_gateway.py` remains the only
module that imports CINDER directly. The gateway exposes the installed package
version, simulation-input schema version, and simulation-result contract version
as runtime identity.

These are intentionally separate concepts:

```text
CINDER package version              implementation/provenance of the mechanics package
simulation case schema version      schema of the frozen input document
simulation result contract version  schema of the projected result artifact
```

A result-contract change therefore does not require changing how the mechanical
solver is called. Database-backed runs record all three identities, and cache
lookups include them. The projected result's own `contract_version` is checked
before it is persisted, preventing a result from being stored under the wrong
version metadata.

The backend does not reinterpret new result fields. Additions such as compact
CINDER domains/fields are part of the JSON-safe result projection returned by
`CinderGateway.run_simulation()` and are persisted/passed through as ordinary
result artifact data.

CINDER exposes `SIMULATION_CASE_SCHEMA_VERSION` and
`SIMULATION_RESULT_CONTRACT_VERSION` directly. The backend pins one exact CINDER
package version and does not carry compatibility aliases for older package
contracts.

CINDER also owns machine-readable JSON Schema for its assembly, simulation-case,
and simulation-result documents. `export_contract_artifacts` writes those
schemas together with backend OpenAPI as ephemeral build artifacts. Frontend
TypeScript generation consumes them directly; the backend does not re-declare
CINDER result/domain/field structures.
