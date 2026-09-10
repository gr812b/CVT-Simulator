# Results against CINDER 1.1.2

This directory is the frozen results workspace for the published
**CINDER 1.1.2** mechanics.

```text
CINDER source tag: cinder-v1.1.2
tag commit:        7637a38b4fb9ec21dfb953c1c80a27ec5f389654
PyPI package:      cinder-cvt==1.1.2
Python:            3.12
NumPy:             2.5.2
SciPy:             1.18.1
Matplotlib:        3.11.1
```

Every generated result in this directory must run against the installed
`cinder-cvt==1.1.2` wheel. Do not add the repository's live `cvtModel/src` tree
to `PYTHONPATH`, and do not silently migrate artifacts from an earlier release.

## Environment

From repository root on Windows:

```powershell
py -3.12 results/cinder-v1.1.2/bootstrap.py
results\cinder-v1.1.2\.venv\Scripts\Activate.ps1
python results/cinder-v1.1.2/verify_environment.py
```

macOS/Linux:

```bash
python3.12 results/cinder-v1.1.2/bootstrap.py
source results/cinder-v1.1.2/.venv/bin/activate
python results/cinder-v1.1.2/verify_environment.py
```

The bootstrap recreates only this release's `.venv`, installs the frozen
requirements from PyPI, and verifies that CINDER is not coming from a local or
editable checkout.

## Frozen defaults

`defaults/baja_reference_simulation_case.json` is the authoritative executable
Baja baseline. It contains the complete geometry, contact law, drivetrain
inertias, pulley mechanisms, engine boundary, vehicle/load model, initial state,
integrator settings, and reporting settings.

`defaults/baja_reference_tuning.json` is a human-readable tuning manifest. It is
not a second executable source of truth.

See [`defaults/README.md`](defaults/README.md) and
[`defaults/provenance.json`](defaults/provenance.json).

## Maintained studies

### Mechanical-energy consistency

```powershell
python results/cinder-v1.1.2/studies/energy-consistency/verify_study.py
python results/cinder-v1.1.2/studies/energy-consistency/run.py
```

This is the formal release-level work/energy audit. It accounts for boundary
work, stored kinetic/conservative energy, kinetic-slip dissipation, and discrete
impact/capture losses; localizes continuous residuals; checks exact event
closure; and repeats the calculation under quadrature and ODE refinement.

It is deliberately neutral about the source of a residual. The study reports
the unexplained remainder rather than applying a candidate missing-power
correction.

### Ballew 2015 model-to-model benchmark

```powershell
python results/cinder-v1.1.2/studies/ballew-2015/verify_study.py
python results/cinder-v1.1.2/studies/ballew-2015/run.py
```

This regenerates the force-replay and reconstructed closed-loop comparison
against Ballew's simulated Figure 41/45 traces using CINDER 1.1.2. It remains a
**model-to-model comparison**, not experimental validation.

### Launch then hill climb

```powershell
python results/cinder-v1.1.2/studies/launch-hill-climb/run.py
```

This example derives from the same frozen Baja baseline and changes only the
declared road programme and end time.

## Result-tree rule

Each CINDER release owns a separate sibling under `results/`. Existing release
artifacts are immutable historical results; a new CINDER version gets fresh
study executions and fresh generated artifacts.

Study runners should save the fully resolved input/provenance beside their
results so a figure or metric can always be traced back to the exact release and
execution settings.
