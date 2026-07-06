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
