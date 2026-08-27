# Fixed-pivot roller flyweight

CINDER models a specific mechanism: a rigid flyweight pivots about a fixed
pivot on the pulley while a finite-radius roller follows a physical ramp
carried by the translating movable sheave. This is deliberately **not** a
universal centrifugal-actuator abstraction.

For the local closing coordinate `x`, the compiled mechanism map returns

```text
q(x), q'(x), q''(x), J(x), J'(x), I
```

and the mounted element contributes

```text
F_fly = 1/2 omega^2 J'
        - I q'^2 x_ddot
        - I q' q'' x_dot^2

T_shaft,reaction = -J alpha - J' x_dot omega
```

## Physical scope and assumptions

The current mechanism assumes:

1. the flyweight pivot is fixed to the pulley body;
2. the ramp translates rigidly with the movable sheave;
3. pivot-to-roller-centre distance is rigid and constant;
4. the roller has a finite radius;
5. the mechanism is planar in the axial-radial section;
6. repeated flyweights are identical and circumferentially symmetric, or
   arranged so omitted cross/gyroscopic terms cancel;
7. ramp contact is frictionless in the force law;
8. roller spin inertia, bearing losses, local contact compliance,
   structural flex, backlash, and manufacturing clearance are not resolved;
9. the selected contact branch remains compressive. A negative solved
   flyweight force is **not** clipped and means the assumed contact topology
   is inadmissible.

These are model-scope assumptions, not hidden numerical shortcuts.

## Contact geometry and branch selection

`PivotedRollerFollowerGeometrySpec` contains the fixed pivot, rigid arm
length, roller radius, Point A / ramp placement, physical ramp profile,
physical axial direction of increasing ramp coordinate, and active local
pulley travel.

Candidate contacts are intersections of the finite-roller offset of the
physical ramp with the rigid arm circle.

More than one instantaneous mathematical arm orientation may exist. That is
not itself a double contact. Construction:

1. enumerates all contacts at `axial_position_min`;
2. selects the candidate with the smallest `q`;
3. follows that branch continuously as local closure increases;
4. never re-selects the minimum root independently at every position.

A **true double contact** is different: one already-selected roller pose
touches two distinct portions of the ramp simultaneously. That is rejected.

Sharp physical corners have an exact finite-roller corner-contact solution
for geometry diagnostics. The acceleration-level production map, however,
requires a smooth ramp.

## Dynamic smoothness requirement

The force law retains `q''(x)`. The exact roller-offset construction uses
the physical ramp through its third derivative. A raw slope, curvature, or
third-derivative discontinuity therefore must not silently enter the
runtime map.

For a piecewise physical ramp, production construction requires **C3
continuity** through active junctions.

`C3TransitionSegment.between_segments(...)` creates a short sixth-order
profile whose first, second, and third derivatives exactly match the
neighboring ramp segments at both ends.

The current provisional Baja geometry uses:

```text
linear:      20 deg, 5 mm
C3 blend:             3 mm
circular:    35 deg -> 10 deg, 30 mm
```

The 3 mm blend is a provisional geometry approximation, not a measured
hardware dimension.

## Mass representation: exact route and explicit approximation

The runtime dynamics do **not** fundamentally assume a point mass or a
uniform rod. `FlyweightMassGeometry` stores body-fixed first and second
mass moments for one flyweight plus the repeated flyweight count. These
determine `I_f`, `J_f(q)`, and `dJ_f/dq`.

### Higher-fidelity route: direct mass moments

If CAD or measured mass properties are available, supply the mass, first
moments, second moments, product moment, and circumferential second moment
directly. Detailed arm shape, thickness, holes, roller hardware, and tuning
weights are then represented to the fidelity of those moments.

### Practical route: uniform arm + concentrated tip hardware

`uniform_slender_arm_with_concentrated_tip_hardware(...)` is the explicit
simplified measurement model.

It assumes:

- arm/body mass is uniformly distributed along the pivot-to-roller-centre
  line;
- roller/bearing mass is concentrated at the roller-centre station;
- bolt mass is concentrated there;
- nut/washer mass is concentrated there;
- other fixed tip hardware is concentrated there;
- variable tuning mass is concentrated there;
- finite radii and centroidal inertias of those tip parts are neglected;
- arm thickness, cut-outs, and nonuniform arm mass distribution are
  neglected.

This reduction is intentionally named so it cannot be mistaken for exact
hardware geometry.

A large tuning weight near the tip often makes its parallel-axis `m L_f^2`
contribution much larger than small centroidal corrections from individual
bolt/nut/roller radii. That is a practical reason the approximation may be
adequate; it is not a universal guarantee. Use direct mass moments when the
correction matters.

Flyweight mass represented here must not also appear in moving-sheave mass
or constant pulley inertia.

### Literature context

Skinner (2020) likewise does not resolve individual fastener or roller
rigid-body inertias. His quasi-static model uses flyweight mass at its
working radius and a separate link mass at the link centre. The present
simplified input model is comparable in measurement burden, while the
direct-moment route can retain substantially more distributed-mass detail.

## Full-range construction audit

`PivotedRollerFollowerGeometry.audit_operating_interval()` returns a
structured `FixedPivotValidationReport` suitable for a CLI, backend route,
or future component editor. The production
`PivotedRollerFollowerFlyweightMap` runs this audit before accepting its
runtime spline.

The audit checks the declared full operating interval for:

- C3 ramp continuity;
- availability of the ramp third derivative;
- contact existence at the start;
- smallest-q branch selection and continuous branch following;
- branch coverage through the entire declared travel;
- finite positive `dq/dx`;
- finite `d2q/dx2`;
- rigid arm-length residual;
- roller-offset regularity;
- same-pose double contact / ramp interference;
- proximity to finite ramp endpoints;
- alternate mathematical configurations.

It retains metrics even for valid geometries:

```text
minimum q'
maximum |q''|
maximum rigid-arm error
minimum roller-offset regular factor
minimum ramp endpoint margin
maximum number of mathematical contact candidates
```

Errors make `report.require_valid()` raise and the runtime map is not
created. Warnings remain visible for the UI/design process.

## Geometry validation is not force admissibility

The construction audit cannot prove compressive contact for every future
dynamic state because `F_fly` depends on `omega`, `x_dot`, and `x_ddot` as
well as geometry.

`FixedPivotFlyweightForce.has_compressive_contact()` remains the unilateral
contact check. A negative value means the constrained roller would have to
pull on the ramp. It must never be hidden with `max(0, F)`. Until a
dedicated lift-off/re-impact mode exists, such a state is an explicit
model-admissibility failure.

## Intended future input-page workflow

A future fixed-pivot component editor should use the same production
geometry and audit code as the solver:

1. user edits pivot, Point A, arm, roller, ramp, and mass inputs;
2. visualizer draws the selected branch and alternate mathematical
   configurations;
3. full-range construction audit runs on every meaningful change;
4. errors are shown prominently and the component cannot be saved/run;
5. warnings and validation metrics remain visible;
6. only audit-valid geometry is compiled into `q(x), J(x), I`.

The visualizer is therefore a view of the production geometry contract, not
a second independent mechanism implementation.
