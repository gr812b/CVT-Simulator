# Getting started with CINDER

## Install

```bash
python -m pip install cinder-cvt==1.0.0
```

Verify the installed version:

```bash
python -c "import cinder; print(cinder.__version__)"
```

## Mechanical composition

CINDER separates the CVT itself from the machines and vehicle attached to its
shafts:

```text
CVTAssemblySpec      physical CVT hardware and contact data
MechanicalCVTPlant   five-state CVT mechanics
Shaft boundaries     engine, vehicle, dyno, brake, motor, etc.
Host                 non-CVT states required by those boundaries
Composed system      CVT + shaft boundaries + host state
```

The CVT state is

```text
[primary speed, secondary speed, belt speed, shift position, shift speed]
```

Shaft angle, vehicle position, and other external states belong to the host,
not to the five-state CVT plant.

## Main Python surface

Core mechanics and execution objects are available from `cinder`:

```python
from cinder import (
    ComposedCVTHybridSystem,
    FullThrottleEngineBoundary,
    LockedFinalDriveShaftBoundary,
    MechanicalCVTPlant,
    SecondaryShaftAngleHost,
)
```

A plant can be composed with external shaft boundaries:

```python
plant = MechanicalCVTPlant.from_assembly(assembly)

system = ComposedCVTHybridSystem.from_plant(
    plant=plant,
    primary_boundary=primary_boundary,
    secondary_boundary=secondary_boundary,
    host=SecondaryShaftAngleHost(),
)
```

Shift stops and the primary dead zone are physical geometry, not solver knobs:

```text
lower stop        s = 0
engagement        s = geometry.deadzone_shift
upper stop        s = geometry.max_shift
```

Belt traction limits come from `BeltContactSpec`; the runtime contact closure is
constructed from those physical contact values.

## Public saved documents

Use `cinder.contracts` when a simulation must be saved, validated, exchanged, or
reproduced from JSON:

```python
from cinder.contracts import (
    decode_simulation_case_document,
    validate_simulation_case_document,
)
```

See `PUBLIC_CONTRACTS.md` for the version-one document format.

## Static studies

Use `cinder.studies` for supported geometry and actuator studies that do not
require a time integration.

## Reference case

A checkout of the source repository contains a current physical fixed-pivot
reference simulation:

```bash
python cvtModel/examples/quickstart.py --run
```

That script imports the installed CINDER distribution; it does not use the
frontend or backend.
