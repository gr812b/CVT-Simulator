# CINDER 1.1.2 studies

Studies in this directory are reproducible analyses generated against the
frozen `cinder-cvt==1.1.2` release environment.

## Current studies

- `energy-consistency/` — release-level mechanical-energy closure, event
  consistency, quadrature refinement, and solver refinement.
- `ballew-2015/` — source-constrained model-to-model literature benchmark.
- `actuator-dynamics/` — official four-part study of the primary flyweight and
  secondary helix dynamic couplings:
  1. Baja baseline ablation;
  2. coupling-energy/generalized-inertia decomposition;
  3. equation-derived quasi-static validity envelopes;
  4. controlled transient validation at achieved dynamic-correction levels.
- `launch-hill-climb/` — retained for later mechanism-resolved narrative work.

## Result-study rules

A normal study should:
1. identify the exact frozen CINDER release;
2. record complete provenance and intentional overrides;
3. use installed release mechanics rather than a mutable local `src/cinder`;
4. retain raw machine-readable outputs needed to remake figures;
5. distinguish verification, model-to-model comparison, and physical claims.

A mechanism study may use release-internal inspection where quantities are not
part of the ordinary serialized report contract, provided the hooks are
documented and the frozen published package is not altered.

The actuator study additionally source-locks its pre-existing baseline utility
scripts to the release tag while keeping its new result logic local to the
release-scoped results tree.
