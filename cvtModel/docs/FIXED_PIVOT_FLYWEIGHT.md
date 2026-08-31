# Fixed-pivot roller flyweight

CINDER models a rigid flyweight pivoted to the pulley body while a finite-radius
roller follows a ramp carried by the translating movable sheave.

For local pulley closure `x`, the compiled mechanism map provides

```text
q(x), q'(x), q''(x), J(x), J'(x), I
```

and the mounted flyweight contributes

```text
F_fly = 1/2 omega^2 J'
        - I q'^2 x_ddot
        - I q' q'' x_dot^2

T_shaft,reaction = -J alpha - J' x_dot omega
```

The same mechanism therefore contributes both axial clamping force and dynamic
shaft coupling.

## Physical scope

The current mechanism assumes:

1. the flyweight pivot is fixed to the pulley body;
2. the ramp translates rigidly with the movable sheave;
3. pivot-to-roller-centre distance is rigid and constant;
4. the roller has finite radius;
5. the mechanism is planar in the axial-radial section;
6. repeated flyweights are identical and circumferentially symmetric, or are
   arranged so omitted cross/gyroscopic terms cancel;
7. ramp contact is frictionless in the force law;
8. roller spin inertia, bearing losses, local compliance, structural flex,
   backlash, and manufacturing clearance are not resolved;
9. the selected contact branch must remain compressive.

A negative solved flyweight reaction is not clipped. It means the assumed
contact topology is dynamically inadmissible.

## Contact geometry and branch selection

`PivotedRollerFollowerGeometrySpec` defines the fixed pivot, arm length, roller
radius, ramp placement/profile, ramp direction, and active pulley travel.

Candidate contacts are intersections of the finite-roller offset of the ramp
with the rigid arm circle. The production geometry:

1. enumerates candidates at the start of travel;
2. selects the intended initial branch;
3. follows that branch continuously through travel;
4. does not re-select an arbitrary instantaneous root at every position.

A true same-pose double contact is rejected.

## Smoothness requirement

The dynamic force law retains `q''(x)`, and the finite-roller construction
depends on the ramp through its third derivative. Active piecewise ramp
junctions therefore require C3 continuity.

`C3TransitionSegment.between_segments(...)` creates a derivative-matched blend.

The CINDER v1 Baja reference profile is

```text
linear:      35 deg, 5 mm
C3 blend:             3 mm
circular:    35 deg -> 20 deg, 30 mm
```

The 3 mm blend is a geometry approximation rather than a measured hardware
dimension.

## Mass representation

`FlyweightMassGeometry` stores body-fixed first and second mass moments for one
flyweight and the repeated flyweight count. These determine `I`, `J(q)`, and
`dJ/dq`.

When detailed mass properties are available, callers can provide those moments
directly.

The practical helper

```text
uniform_slender_arm_with_concentrated_tip_hardware(...)
```

represents the arm/body as a uniform slender member and the roller/fastener/
tuning hardware as concentrated tip mass. The CINDER v1 Baja reference uses:

```text
arm/body mass per flyweight:     13.646 g
tip hardware per flyweight:     250.000 g
total represented per flyweight:263.646 g
number of flyweights:             3
```

Flyweight mass represented by this mechanism must not also be included in
constant pulley inertia or moving-sheave mass.

## Construction audit

`PivotedRollerFollowerGeometry.audit_operating_interval()` checks the declared
operating interval before a runtime map is accepted. The audit covers:

- C3 ramp continuity;
- ramp derivative availability;
- contact existence and branch coverage;
- finite positive `dq/dx`;
- finite `d2q/dx2`;
- rigid arm-length residual;
- roller-offset regularity;
- same-pose double contact/interference;
- finite ramp-end margin;
- alternate mathematical configurations.

The report retains quantitative margins even for valid geometries.

## Dynamic contact admissibility

A valid geometry does not guarantee contact for every dynamic state because the
reaction also depends on `omega`, `x_dot`, and `x_ddot`.

`FixedPivotFlyweightForce.has_compressive_contact()` is the unilateral dynamic
contact check. A negative value means the constrained roller would have to pull
on the ramp. Until a lift-off/re-impact topology is explicitly modeled, that
state is rejected rather than hidden with `max(0, F)`.
