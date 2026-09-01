# CINDER

**CINDER** is a mechanics-first Python model for rubber V-belt continuously
variable transmissions (CVTs). The installed package is imported as `cinder`.

CINDER models the CVT as a mechanical plant with explicit pulley geometry,
belt contact, clamping mechanisms, inertias, shaft boundaries, and hybrid
contact/operating modes. The package is independent of the CVT-Simulator web
frontend and backend.

## Install

```bash
python -m pip install cinder-cvt==1.0.1
```

Verify the installed distribution:

```bash
python -c "import cinder; print(cinder.__version__)"
```

Expected output for this release:

```text
1.0.1
```

Runtime dependencies are intentionally small:

- NumPy
- SciPy

## Public Python API

CINDER v1 has three supported import surfaces:

- `cinder` — core mechanics, composed systems, shaft boundaries, hosts, and
  hybrid execution entry points.
- `cinder.contracts` — versioned JSON-safe assembly/simulation documents,
  validation, schema information, and result projection.
- `cinder.studies` — supported static geometry and actuation study APIs.

Modules beneath these public surfaces remain available to advanced users, but
deep implementation-module paths are not the compatibility boundary for v1.

## Run the reference example

The source repository contains a current fixed-pivot Baja reference case:

```bash
python cvtModel/examples/quickstart.py --run
```

The example imports the installed `cinder` package. It does not require the
frontend or backend.

## Documentation

- [Getting started](https://github.com/gr812b/CVT-Simulator/blob/cinder-v1.0.1/cvtModel/docs/GETTING_STARTED.md)
- [Public document contracts](https://github.com/gr812b/CVT-Simulator/blob/cinder-v1.0.1/cvtModel/docs/PUBLIC_CONTRACTS.md)
- [Simulation-document JSON Schema](https://github.com/gr812b/CVT-Simulator/blob/cinder-v1.0.1/cvtModel/docs/DOCUMENT_SCHEMA.md)
- [Geometry study API](https://github.com/gr812b/CVT-Simulator/blob/cinder-v1.0.1/cvtModel/docs/GEOMETRY_STUDY_API.md)
- [Actuation study API](https://github.com/gr812b/CVT-Simulator/blob/cinder-v1.0.1/cvtModel/docs/ACTUATION_STUDY_API.md)
- [Fixed-pivot flyweight mechanics](https://github.com/gr812b/CVT-Simulator/blob/cinder-v1.0.1/cvtModel/docs/FIXED_PIVOT_FLYWEIGHT.md)
- [Hybrid impact mechanics](https://github.com/gr812b/CVT-Simulator/blob/cinder-v1.0.1/cvtModel/docs/HYBRID_IMPACT_MECHANICS.md)

## Repository-only material

The monorepo also contains `launchTools`, `tools`, validation artifacts, the
backend, and the frontend. Those directories are useful to the project but are
not part of the `cinder-cvt` wheel or source distribution.

## License

CINDER is licensed under the Creative Commons
Attribution-NonCommercial 4.0 International license (CC BY-NC 4.0).
Commercial use requires separate permission. See `LICENSE`.
