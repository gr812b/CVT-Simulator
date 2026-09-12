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
