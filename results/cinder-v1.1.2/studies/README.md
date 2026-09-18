# CINDER 1.1.2 studies

Studies in this directory are reproducible analyses generated against the
frozen `cinder-cvt==1.1.2` release environment plus the declared v1.1.2
**results reference-model policy**.

The general results reference uses a bilateral/slotted secondary helix while
preserving the production signed torque/force equations. This keeps one-flank
helix lift-off from obscuring belt/closure questions. A study specifically about
helix topology should opt out and compare the two designs explicitly.

## Current studies

- `energy-consistency/` — release-level mechanical-energy closure, event
  consistency, quadrature refinement, and solver refinement.
- `mechanical-invariants/` — operating-domain mechanical/admissibility audit,
  rare contact-mode reproduction anchors, and capability interpretation.
- `closure-conditioning/` — conditioning/well-posedness of the engaged closure.
- `solver-convergence/` — wide solver-control convergence.
- `ballew-2015/` — source-constrained model-to-model literature benchmark.
- `actuator-dynamics/` — actuator dynamic/coupling studies and commercial-case
  reconstruction.
- `launch-hill-climb/` — retained for mechanism-resolved narrative work.

## Shared reference-model rule

Studies derived from the shared Baja default use `defaults.reference_model.decode_reference_case` and inherit the bilateral/slotted secondary helix automatically. Explicitly custom assemblies remain independent.

## Result-study rules

A normal study should:

1. identify the exact frozen CINDER release;
2. record complete provenance and intentional results-reference overrides;
3. use installed release mechanics rather than mutable local `src/cinder`;
4. retain raw machine-readable outputs needed to remake figures;
5. distinguish verification, model-to-model comparison, and physical claims;
6. distinguish **loss of an assumed topology** from numerical failure or proof
   that the corresponding real-hardware motion is impossible.

A mechanism study may use release-internal inspection where quantities are not
part of the ordinary serialized report contract, provided the hook is documented
and the frozen published package is not altered.

## Common study contract

The maintained v1.1.2 studies use the same repository vocabulary:

- `run.py` — canonical maintained-study entry point. A complete run must generate the maintained result set and every candidate figure/table that could later be selected for the manuscript. It does not run `exploration/`.
- `verify_study.py` — study-local health/provenance checks.
- `study.json` — common outer manifest schema plus study-specific payload.
- `infrastructure/` — reusable support code; not a standalone scientific run.
- `experiments/` — maintained protocol/case-family implementations.
- `analysis/` — maintained synthesis, metrics, and candidate figure/table generation.
- `exploration/` — discovery history intentionally excluded from the canonical run.
- `provenance/` — external-source, reconstruction, or source-registration material.
- `tests/` — study-local automated tests.
- `artifacts/` — generated outputs; not source-controlled.

Interpretation/recap PDFs remain at study root until the corresponding Chapter 4 section is frozen. `analysis/` means maintained, **not paper-official**. All study manifests therefore use `paper_role: "undecided"` until figure/table selection is complete. Any older study-local use of words such as `official` continues to mean maintained within that study; it does not select an item for the manuscript.

