# CINDER results

This directory contains reproducible result studies generated against released
versions of CINDER.

Each top-level version directory is named for the CINDER Git release tag used
by the studies inside it:

```text
results/
├── README.md
└── cinder-v1.0.0/
    ├── README.md
    ├── requirements.txt
    ├── bootstrap.py
    ├── verify_environment.py
    └── studies/
        └── README.md
```

A future CINDER release gets a new sibling directory such as
`cinder-v1.0.1/`. Existing studies are not migrated to newer CINDER code.

## Reproducibility rule

`results/cinder-v1.0.0/` uses the published PyPI distribution:

```text
cinder-cvt==1.0.0
```

It must not use `cvtModel/src`, an editable install, or `PYTHONPATH`.

The directory name identifies the exact source checkpoint (`cinder-v1.0.0`);
the requirements file identifies the exact installed Python package and
numerical environment.

## Study layout

Each independent result or tightly related result family lives under
`studies/`:

```text
studies/
└── study-name/
    ├── README.md
    ├── run.py
    ├── inputs/
    └── artifacts/
```

Only create `inputs/` or `artifacts/` when a study needs them. Temporary solver
output, caches, and exploratory intermediates belong in a study-local `work/`
directory, which is ignored by Git.

Do not create one global output directory for unrelated studies. Each study
should carry the code, committed inputs, and committed artifacts needed to
understand and regenerate that result.

Shared result-layer helpers should only be introduced once multiple studies
genuinely need them. CINDER mechanics must continue to come from the published
package rather than copied or reimplemented result-side.

## Adding a future CINDER release

1. Create `results/<cinder-release-tag>/`.
2. Pin the matching `cinder-cvt` version from PyPI.
3. Pin the Python and numerical-library versions for that result series.
4. Create a fresh release-local `.venv`.
5. Verify that `cinder` imports from that `.venv`, not from the repository.
6. Put new studies only under that release directory.
