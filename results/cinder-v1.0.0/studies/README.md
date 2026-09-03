# CINDER 1.0.0 studies

Most studies derive from a frozen document in `../defaults/` and record only
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

`run.py` should:

1. verify the release environment;
2. load the named baseline;
3. apply only the declared study overrides;
4. validate through `cinder.contracts`;
5. run CINDER;
6. save the fully resolved simulation document;
7. save machine-readable result data;
8. generate the study's plots/tables.

This makes the baseline tune common and reviewable while leaving each result
with a complete record of the exact input it executed.

## Studies that require public Python extension points

A literature reconstruction or mechanism study may require a custom boundary,
host, actuator, or force law that CINDER deliberately supports as a Python
extension point but does not serialize as a built-in simulation-case document.
Such a study should **not** invent a fake serialized baseline merely to match the
ordinary layout.

Instead it must:

1. document why the required object is outside the built-in serialization
   contract;
2. run only the frozen release environment for that results version;
3. keep the smallest possible study-specific extension implementation local to
   the study;
4. validate the assembled CINDER specification through public contracts;
5. save a complete JSON-safe resolved parameter/provenance document alongside
   the result;
6. keep all source/reference data required for the study reproducible from the
   study directory itself.

`ballew-2015/` is the reference example for this pattern because its force-replay
and reconstructed PI protocols require study-specific axial-force/host objects.
