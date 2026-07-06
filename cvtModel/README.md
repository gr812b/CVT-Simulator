# CVT Model — CINDER

This repository contains **CINDER**, a mechanics-first Python package for
rubber V-belt CVTs, together with project-local tools used to exercise and
compare the model.

The public Python package is imported as `cinder`. Its installed code lives
only under `src/cinder`.

## Repository layout

```text
cvtModel/
├─ launchTools/                 # project-local launch/tuning/plotting tooling
├─ src/
│  ├─ cinder/                   # installed CINDER package
│  └─ cvt_simulator/            # legacy package; retained temporarily, not installed
├─ test/
│  ├─ cinder/                   # CINDER regression tests
│  └─ cvt_simulator/            # legacy tests; retained temporarily
├─ docs/                        # public CINDER documentation
├─ examples/                    # small CINDER-only runnable examples
├─ README.md
├─ setup.py
├─ setup.cfg
└─ pyproject.toml
```

`launchTools` is intentionally outside the package. It may import CINDER, but
it is not imported by CINDER and is not part of the CINDER installation or
public API.

`src/cvt_simulator` remains on disk during migration, but this setup installs
only `cinder`. That prevents the retired package from becoming an accidental
runtime dependency. Once the migration is complete, remove
`src/cvt_simulator` and `test/cvt_simulator` in one cleanup change.

## Setup

From this repository root:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On macOS/Linux, activate with:

```bash
source .venv/bin/activate
```

An editable install means imports resolve to the current `src/cinder` source;
you do not need to set `PYTHONPATH` for normal development.

## Verify CINDER

```powershell
python examples/quickstart.py
python -m pytest
python -m coverage run -m pytest
python -m coverage report
```

The default test target is `test/cinder`. The retained legacy tests are not run
by default.

## Format and lint CINDER

```powershell
black --check src/cinder test/cinder examples
flake8 src/cinder test/cinder examples
```

## Learn the public API

- [Getting Started](docs/GETTING_STARTED.md)
- [Public Contract API](docs/PUBLIC_CONTRACT_API.md)
- [Geometry Study API](docs/GEOMETRY_STUDY_API.md)
- [Actuation Study API](docs/ACTUATION_STUDY_API.md)

CINDER’s stable external boundary is `cinder.contracts`. It provides versioned
assembly documents, component discovery, preflight validation, JSON-safe
study/result projection, and standard simulation summaries.
