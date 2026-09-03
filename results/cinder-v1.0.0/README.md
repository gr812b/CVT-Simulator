# Results against CINDER 1.0.0

Frozen execution environment:

```text
CINDER source tag: cinder-v1.0.0
PyPI package:       cinder-cvt==1.0.0
Python:             3.12
NumPy:              2.5.2
SciPy:              1.18.1
Matplotlib:         3.11.1
```

## Environment

From repository root:

```powershell
py -3.12 results/cinder-v1.0.0/bootstrap.py
results\cinder-v1.0.0\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3.12 results/cinder-v1.0.0/bootstrap.py
source results/cinder-v1.0.0/.venv/bin/activate
```

The bootstrap recreates only this release's `.venv`, installs from the public
PyPI index, and runs `verify_environment.py`.

## Frozen defaults

See [`defaults/README.md`](defaults/README.md).

`defaults/baja_reference_simulation_case.json` is the authoritative complete
executable baseline. It contains geometry, friction, inertias, primary and
secondary mechanisms, engine curve/inertia, vehicle/final-drive/road-load
inputs, initial state, solver settings, and report settings.

`defaults/baja_reference_tuning.json` preserves the more intuitive physical
tuning quantities used to construct the encoded mechanism inputs.

## Sample study

Run:

```bash
python results/cinder-v1.0.0/studies/launch-hill-climb/run.py
```

It starts from the frozen baseline and changes only:

- total simulation time: 10 s;
- road: 0° from 0–15 m;
- road: 15° from 15 m onward.

The study writes the resolved complete input, projected CINDER result, CSV
report, summary, and individual PNG plots under its `artifacts/` directory.
