# CINDER 1.1.2 studies

Studies in this directory are reproducible analyses generated against the frozen
`cinder-cvt==1.1.2` release environment.

Most studies derive from a complete document in `../defaults/` and record only
their intentional changes in `study.json`.

Recommended layout:

```text
study-name/
├── README.md
├── study.json
├── run.py
├── artifacts/
└── work/
```

A normal study runner should:

1. verify the release environment;
2. load its named frozen baseline;
3. apply only declared study overrides;
4. validate through CINDER's public contracts;
5. run the installed CINDER release;
6. save the fully resolved executed input;
7. save machine-readable results and provenance;
8. generate reader-facing plots/tables from those results.

## Current studies

- `energy-consistency/` — release-level mechanical-energy closure, event
  consistency, quadrature refinement, and solver refinement.
- `ballew-2015/` — source-constrained model-to-model literature benchmark.
- `launch-hill-climb/` — simple baseline-derived dynamic example.

## Studies requiring Python extension points

A literature reconstruction or mechanism study may require a custom boundary,
host, actuator, or force law that CINDER deliberately supports as a Python
extension point but does not serialize as a built-in simulation-case document.
Such a study should not invent a fake serialized baseline merely to match the
ordinary layout.

Instead it must:

1. document why the required object is outside the built-in serialization
   contract;
2. run only the frozen release environment for this results version;
3. keep the smallest possible study-specific extension implementation local to
   the study;
4. validate the assembled CINDER specification through public contracts;
5. save a complete JSON-safe resolved parameter/provenance document alongside
   the result;
6. keep all source/reference data required for the study reproducible from the
   study directory itself.

`ballew-2015/` is the reference example for this pattern.

## Release-internal inspection

A correctness study may need to inspect quantities that are not currently
serialized as ordinary report signals—for example, exact transition kinetic
energy or arbitrary-time solved contact power. Such inspection is acceptable
only when it:

- runs against the frozen published package;
- does not alter the mechanics or inject a local source tree;
- documents the internal hooks it reads;
- records the exact release provenance.

`energy-consistency/` follows this pattern.
