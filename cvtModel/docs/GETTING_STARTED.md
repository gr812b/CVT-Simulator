# Getting started with CINDER

CINDER's simulation API is now built around a five-state mechanical CVT plant
hosted inside a composed system.

```text
CVTAssemblySpec      physical CVT: geometry, inertias, contact, actuators
MechanicalCVTPlant   five-state CVT mechanics
Shaft boundaries     engine, vehicle, dyno, tire, brake, motor, etc.
Host                 non-CVT states required by the boundaries
Composed system      CVT + shaft boundaries + host state
```

The CVT state is:

```text
[primary speed, secondary speed, belt speed, shift position, shift speed]
```

Shaft angle, vehicle position, and tire/suspension states are host states, not
CVT states.

## Run the example

```bash
PYTHONPATH=src python examples/quickstart.py --run
```

The example loads `examples/baja_baseline_simulation_case.json`, validates it,
decodes a `ComposedCVTHybridSystem`, runs it, and prints report columns.

## Build directly in Python

```python
plant = MechanicalCVTPlant.from_assembly(assembly)

system = ComposedCVTHybridSystem.from_plant(
    plant=plant,
    primary_boundary=FullThrottleEngineBoundary(
        engine_curve,
        equivalent_rotational_inertia=engine_inertia,
    ),
    secondary_boundary=LockedFinalDriveShaftBoundary(
        road_load=road_load,
        road_profile=ConstantGradeRoadProfile(),
        direct_secondary_shaft_inertia=gearbox_input_inertia,
    ),
    host=SecondaryShaftAngleHost(),
)
```

Shift stops and the dead zone are not solver knobs. They are read from the
assembly geometry: lower stop is `s = 0`, engagement is
`geometry.spec.deadzone_shift`, and upper stop is `geometry.spec.max_shift`.

Friction coefficients belong to `BeltContactSpec`; CINDER constructs the
internal traction closure from those physical contact values.
