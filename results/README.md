# CINDER results

This tree contains reproducible studies generated against released CINDER
versions. The version directory is part of the provenance:

```text
results/
└── cinder-v1.0.0/
    ├── defaults/       # frozen reference system/tune inputs
    ├── studies/        # result studies derived from those defaults
    ├── requirements.txt
    ├── bootstrap.py
    └── verify_environment.py
```

A new CINDER release gets a new sibling directory. Existing studies are never
silently migrated to newer CINDER mechanics.

## Defaults versus studies

`defaults/` owns complete frozen reference configurations. For v1.0.0 the
authoritative executable baseline is a public CINDER simulation-case JSON
document copied from the `cinder-v1.0.0` source tag.

A study should **derive from a named default and change only its declared
variables**. Do not paste an independently maintained full tune into every
study. Each run saves its resolved full simulation document with the artifacts,
so the exact executed input remains inspectable.

## Package provenance

Studies under `cinder-v1.0.0/` execute against the published distribution:

```text
cinder-cvt==1.0.0
```

The release-local bootstrap creates a clean `.venv`; the verifier rejects local
`cvtModel/src`, editable/direct CINDER installs, version drift, and the wrong
Python interpreter.

## Study convention

```text
studies/<study-name>/
├── README.md
├── study.json       # base default + intentional overrides
├── run.py
├── artifacts/       # generated committed results
└── work/            # scratch/intermediate files; ignored
```

Result-only plotting/analysis dependencies belong in the release-level
`requirements.txt`, not in the CINDER package.
