Continuous ODE state
    ↓
`cinder.integration.CVTDynamicState`
    ↓
DynamicsSnapshot
    ↓
`build_state_fixed_equations(snapshot)`
    → five lambda-independent mechanics rows cached for the full RHS evaluation


DynamicsSnapshot + trial signed λp, λs
    ↓
TrialEquationContext
    ↓
three lambda-dependent closure rows
    ↓
8 affine closure rows
    ↓
TrialClosureSystem
    ↓
A z = b
    ↓
TrialClosureResult

Canonical closure basis:

    [ω̈_p, ω̈_s, v̇_b, s̈, τ_p, τ_s, N_p, N_s]

Current fixed-λ row order:

    1. primary shaft rotation                    state-fixed
    2. whole-belt tangential momentum            state-fixed
    3. secondary shaft rotation                  state-fixed
    4. primary physical axial balance            state-fixed
    5. secondary physical axial balance          state-fixed
    6. primary integrated traction resultant     lambda-dependent
    7. secondary integrated traction resultant   lambda-dependent
    8. closed tension-loop compatibility          lambda-dependent

`ContactTractionUtilization` stores the signed effective traction ratios:

    λ_j = Q_j / N_j = τ_j / (r_tau,j N_j).

It is not a commanded percentage. A stick solve finds the static traction
requirement. `ContactTractionLaw` separately decides whether that requirement
lies within physical signed static limits. In a selected slip branch, the law
provides the kinetic lambda magnitude and the stored slip direction supplies
its sign.

`LambdaSearchBounds` is strictly numerical. It intentionally must not be used
as the physical traction limit, because a required stick solution outside
physical capacity is useful information for selecting a slip branch.

## Secondary-shaft attachment boundary

CINDER now keeps its CVT/contact closure independent of the particular load
connected to the secondary shaft.  The eight closure unknowns and all contact,
shift, and regime logic are unchanged.  At each RHS evaluation, a downstream
attachment supplies only:

- added rotational inertia referred to the secondary shaft; and
- signed external torque applied to the secondary shaft.

The normal vehicle configuration is
`cinder.downstream.LockedFinalDriveVehicle`.  It reproduces the former rigid
final-drive mapping: vehicle distance and speed come from secondary angle and
speed, road force is reflected as secondary torque, and vehicle/wheel inertia
is reflected as added secondary inertia.

Preferred new assembly resolves only CVT-side inertias and then attaches the
vehicle:

```python
from cinder.downstream import LockedFinalDriveVehicle
from cinder.dynamics import CVTDynamicsModel
from cinder.inertia import resolve_inertias

inertias = resolve_inertias(
    drivetrain=drivetrain_inertias,
    belt_section=belt_section,
    belt_outer_length=belt_outer_length,
)

model = CVTDynamicsModel(
    geometry=geometry,
    primary_actuator=primary_actuator,
    secondary_actuator=secondary_actuator,
    secondary_helix_profile=helix_profile,
    inertias=inertias,
    engine=engine,
    secondary_attachment=LockedFinalDriveVehicle(
        road_load=road_load,
        road_profile=road_profile,
    ),
)
```

For a direct secondary-shaft or dyno test, use the same CVT model with a
`FixedSecondaryLoad` instead:

```python
from cinder.downstream import FixedSecondaryLoad

model = CVTDynamicsModel(
    ...,
    secondary_attachment=FixedSecondaryLoad(
        external_torque=-12.0,
        added_rotational_inertia=0.03,
    ),
)
```

Vehicle-only observables are intentionally optional.  In a standard locked
vehicle simulation they are available as `snapshot.vehicle_road_load` and
`snapshot.vehicle_distance`; a direct shaft load has no invented vehicle
speed or route position.

The legacy constructor path with `road_load=` and `road_profile=` remains
accepted for existing callers.  It preserves its old reflected-inertia
behavior while callers migrate to the explicit attachment form.
