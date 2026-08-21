# Hybrid impact and capture mechanics

This note documents the momentum treatment used by the current rigid CVT model.
It is intentionally separate from the flyweight-geometry TODO.

## Principle

A topology change is not implemented by independently zeroing or copying scalar
velocities.  The reduced generalized velocity

`u = [omega_p, omega_s, v_b, s_dot]`

is mapped to the physical velocities that actually carry kinetic energy.  The
instantaneous kinetic metric includes the shaft inertias, movable-sheave axial
masses, belt transport mass, movable-sheave rotational inertias, helix
cross-motion, referred boundary inertias, and the current point-mass flyweight
shaft inertias.

For pre/post physical-velocity maps `z_- = J_- u_-` and `z_+ = J_+ u_+`, a
plastic topology capture solves

`(J_+^T W J_+) u_+ = J_+^T W J_- u_-`

with any newly active velocity constraints imposed in the same KKT solve.  This
is the multi-DOF analogue of conserving `m v` when an effective moving mass
changes.

The projection must satisfy:

- every imposed post-event velocity constraint;
- generalized impulse/momentum balance to numerical precision;
- non-increasing kinetic energy for a plastic capture/impact.

Every production reset records these quantities in transition metadata.

## Events

### Primary reaches the belt

The deadzone and engaged geometry are position-continuous but have different
one-sided tangents at `s = s_e`.  Engagement therefore projects the incoming
deadzone momentum onto the engaged tangent instead of copying `s_dot` unchanged.
The existing secondary/belt lock is retained through this capture.

This allows incoming primary axial momentum to become secondary opening,
helix-relative rotation, shaft rotation, belt motion, and remaining shift motion
without creating kinetic energy.

### Secondary reaches its fully closed stop

On a return to minimum ratio the secondary movable member strikes its actual
closed hardware stop.  Relative secondary axial/helix motion is arrested by a
perfectly inelastic impact.  Its angular momentum is transferred into the
secondary shaft/belt system by the same mass-metric projection.  The primary is
not automatically stopped; if unilateral belt contact cannot hold, it separates
and carries its admissible remaining axial momentum into deadzone.

The shrinking make/break sequence at this boundary is the rigid-model analogue
of a dissipative bouncing-contact (a Zeno sequence).  It is completed only when
the remaining shift kinetic energy falls below floating-point energy resolution,
then the ordinary secondary-stop seat is entered.  No Filippov averaged force
field is used.

### Low-ratio seat

The constrained body is the **secondary movable sheave**, because its fully
closed hardware stop supports minimum ratio.  The primary axial force balance
remains an ordinary physical belt/actuator balance.  The secondary axial row is
replaced by `s_ddot = 0`, and the omitted secondary row recovers the unilateral
stop reaction.

### Primary lower metal stop

Arrival at the primary open stop uses the mass-metric perfectly inelastic stop
projection.  Any kinetic couplings represented in the current kinetic metric
participate in the impulse.

### Upper metal stop

Arrival at maximum shift also uses the mass-metric stop projection.  In
particular, killing `s_dot` cannot simply delete the secondary movable member's
helix-relative angular momentum; that momentum is redistributed into the
secondary shaft.  This removes the small energy creation produced by the old
`shift_speed <- 0` reset.

## One-sided geometry

`evaluate_deadzone()` and `evaluate_engaged()` own their respective one-sided
tangents at `s_e`.  Roundoff-sized event-localization excursions are snapped to
the requested side; genuine wrong-topology calls are rejected.  Rejected ODE
trial stages are clipped by the active evaluator rather than changing the raw
event state.

Geometry event indicators use the exact physical surfaces (`s-s_boundary`) but
snap differences of only a few floating-point ULPs to exact zero.  This avoids
a `solve_ivp`/Brent edge case where the step endpoint sees an exact root while
the dense interpolant represents the same endpoint one ULP to the other side.
The snap is independent of velocity and solver tolerance and does not shift or
re-arm the physical event surface.

## Deliberate model approximations still present

These are not hidden conservation errors, but they should remain explicit:

1. **Point-mass flyweights.**  The current model includes their instantaneous
   shaft-axis inertia `m r^2`.  Pivot/radial kinetic energy awaits the future
   `q_f(x), I_f, J_f(x)` geometry derivation.
2. **Rigid belt engagement.**  The primary/belt topology change is represented
   as a plastic tangent-space capture, i.e. the zero-compliance limit.  A real
   belt establishes contact over finite compliance/contact time.
3. **Deadzone belt-secondary lock.**  The reduced deadzone assumes the belt is
   captured to the secondary.  If a transition enters deadzone with a speed
   mismatch, the model performs a momentum-consistent inelastic capture.  A
   higher-fidelity model could retain finite secondary/belt slip instead.
4. **Belt axial inertia and local seating/creep losses.**  These are outside the
   retained formulation and therefore outside the impact kinetic metric.

Legacy scalar stop helpers in `cvt_lower_stop.py` and `cvt_upper_stop.py` are
kept only for old preview/API compatibility.  Production hybrid transitions do
**not** use them; they use `cvt_impact.project_cvt_velocity_topology`.
