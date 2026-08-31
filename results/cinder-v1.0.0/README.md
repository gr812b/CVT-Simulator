# Results against CINDER 1.0.0

This result series is frozen to:

```text
CINDER source tag: cinder-v1.0.0
PyPI distribution: cinder-cvt==1.0.0
Python:             3.12
NumPy:              2.5.2
SciPy:              1.18.1
```

The local `cvtModel/` source tree is deliberately not part of this environment.

## Create the clean environment

Windows:

```powershell
py -3.12 results/cinder-v1.0.0/bootstrap.py
results\cinder-v1.0.0\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3.12 results/cinder-v1.0.0/bootstrap.py
source results/cinder-v1.0.0/.venv/bin/activate
```

`bootstrap.py` deletes and recreates only this directory's `.venv`, then
installs the frozen requirements with isolated pip configuration from the
explicit public PyPI index `https://pypi.org/simple`.

It finishes by running `verify_environment.py`.

## Verify an existing environment

```bash
python results/cinder-v1.0.0/verify_environment.py
```

The verifier requires Python 3.12, exact package versions, an interpreter from
this directory's `.venv`, a `cinder` import from that `.venv`, no
`cvtModel/src` entry on `sys.path`, and no local/direct-install provenance for
`cinder-cvt`.

If verification fails, fix/recreate the environment rather than letting a
study fall back to repository source.

## Add a study

Create a directory under `studies/`:

```text
studies/
└── launch-baseline/
    ├── README.md
    ├── run.py
    ├── inputs/
    └── artifacts/
```

The study README should state the question, inputs, regeneration command, and
meaning of each committed artifact.

If a study adds plotting or analysis dependencies, add them to this release's
`requirements.txt` with exact pins. Do not add result-only dependencies back
into the `cinder-cvt` package.

If a study requires newer CINDER mechanics, create a new
`results/cinder-vX.Y.Z/` tree instead of changing the CINDER pin here.
