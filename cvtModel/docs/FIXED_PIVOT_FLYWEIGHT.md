# Fixed-pivot roller flyweight

CINDER supports the fixed-pivot, translating-ramp mechanism used by the CVT
formulation appendix. This is a mechanism-specific model, not a claim that all
centrifugal clutches share the same internal coordinate.

For the local closing coordinate `x` of whichever pulley hosts the element, the
map returns

`q(x), q'(x), q''(x), J(x), J'(x), I`.

The mounted element contributes

```text
F_fly = 1/2 omega^2 J'
        - I q'^2 x_ddot
        - I q' q'' x_dot^2

T_shaft,reaction = -J alpha - J' x_dot omega
```

The plant supplies `x_ddot` as an affine relation in the shared closure
unknowns. Consequently, mounting this element on the secondary automatically
targets the secondary angular-acceleration column and applies the secondary
`x(s)` mapping. No primary-specific dynamics branch is involved.

## Physical geometry

`PivotedRollerFollowerGeometrySpec` describes:

- a fixed pivot `(x_P, r_P)`;
- a rigid pivot-to-roller-center length;
- the roller radius;
- a physical ramp profile `f(xi)` carried by the movable sheave;
- the ramp's axial and radial reference placement; and
- the active local pulley travel.

The implementation offsets the physical ramp by the roller radius, intersects
that locus with the arm circle, and differentiates the implicit contact
constraint. Construction rejects missing or multiple contacts, roller/ramp
interference, a singular roller offset, folds/dead centres, and branches with
`q'(x) <= 0`.

The exact contact solutions are compiled into a clamped C2 spline for the RHS.
`evaluate_exact()` remains available for CAD checks and derivative regression.
Built-in linear and circular ramp segments provide the third profile derivative
needed by the exact implicit `q''` calculation. Piecewise physical ramps must be
smooth through the active contact region.

## Mass geometry and accounting

`FlyweightMassGeometry` stores the body-fixed first and second mass moments of
one flyweight and the number of circumferentially repeated members. The helper
`uniform_arm_with_end_mass()` implements the appendix's uniform arm plus
concentrated end-mass example.

The model assumes a planar, circumferentially repeated or mirror-symmetric set,
so the retained kinetic energy is

```text
T_f = 1/2 J(x) omega^2 + 1/2 I [q'(x) x_dot]^2.
```

Flyweight mass represented here must not also be included in the translating
movable-sheave mass or a constant pulley inertia.

## Python construction

The dimensions below are illustrative regression geometry, not Baja hardware
data.

```python
from cinder.model.cvt.actuation import (
    AxialSpringForce,
    FixedPivotFlyweightForce,
    FixedPivotFlyweightForceSpec,
    FlyweightMassGeometry,
    PivotedRollerFollowerFlyweightMap,
    PivotedRollerFollowerGeometrySpec,
    PulleyActuator,
)
from cinder.model.cvt.profiles import LinearSegment, PiecewiseRamp

physical_ramp = PiecewiseRamp(
    (LinearSegment(length=0.12, angle_degrees=-30.0),)
)
geometry = PivotedRollerFollowerGeometrySpec(
    pivot_axial_position=0.0,
    pivot_radius=0.05,
    arm_length=0.04,
    roller_radius=0.005,
    ramp_reference_axial_position=0.0,
    ramp_reference_radius=0.05,
    ramp_profile=physical_ramp,
    axial_position_min=0.0,
    axial_position_max=0.02,
    roller_side_sign=-1,
)
mass = FlyweightMassGeometry.uniform_arm_with_end_mass(
    number_of_flyweights=3,
    arm_length=0.04,
    arm_mass_per_flyweight=0.05,
    end_mass_per_flyweight=0.10,
)
mechanism_map = PivotedRollerFollowerFlyweightMap(
    geometry_spec=geometry,
    mass_geometry=mass,
)
flyweight = FixedPivotFlyweightForce(
    FixedPivotFlyweightForceSpec(mechanism_map=mechanism_map)
)

# Use the same composition on primary or secondary.
actuator = PulleyActuator(flyweight, existing_spring)
```

The assembly document kind is `fixed_pivot_roller_flyweight`. Encoding and
decoding preserve the physical geometry, mass moments, validation settings,
and compilation resolution.

## Hybrid events and contact admissibility

Mounted elements expose physical kinetic modes rather than being recognized by
class name. The event metric therefore receives both `J(x)` on the owning shaft
and `I [q'(x) x_dot]^2`, including when the element is mounted on the secondary.

Ramp force remains an affine closure relation and is not silently clipped with
`max(0, F)`. After a solve, `has_compressive_contact()` checks the unilateral
condition. A negative result means the assumed follower-contact topology is not
admissible and should be handled diagnostically or by an explicit future
contact-mode transition.
