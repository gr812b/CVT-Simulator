# Mechanical contract of this study

## Same vehicle and boundary laws

The primary remains `FullThrottleEngineBoundary` with its unmodified reference torque curve and `I_B,p`. The secondary remains `LockedFinalDriveShaftBoundary`, using the reference vehicle, final drive and road-load law. Only its distance-indexed `RoadProfile` is replaced, identically for every tune.

With `k = r_w/G`, the existing host and boundary relations are

- `distance = k psi_s`, `v = k omega_s`, `psi_s_dot = omega_s`;
- `tau_B,s = k F_road(v, gamma(distance))`;
- `I_B,s = I_direct + I_wheel/G^2 + m k^2`.

The host retains the shaft-angle state. Its finish/rollback events terminate observation; neither changes any CVT state, applies an impulse, nor changes a boundary torque.

## Full dynamic actuator identities

Primary `FixedPivotFlyweightForce` is retained exactly. A concentrated tip-mass edit `Delta m` at `u=L, v=z=0` changes

- total per-member mass by `Delta m`;
- first u moment by `L Delta m`;
- second u moment by `L^2 Delta m`.

CINDER derives both centrifugal drive and dynamic inertia from those moments. No change is separately added to the constant shaft inertia. The baseline arm partition is verified before these edits are allowed.

The secondary uses the shared Results `BilateralHelicalTorqueReactionForce`. Its `evaluate` implementation is inherited from the released full dynamic helix law. Signed reaction may be supported by either zero-clearance slot flank. No torque/spring/inertia term is deleted. Changing helix angle therefore changes both torque sensitivity and reflected shift inertia in the ordinary coupled solve.

## What is prescribed versus solved

Prescribed: the physical tune, common initial state, common spatial road, and unchanged full-throttle engine/vehicle parameters.

Solved: clutching, shift history, support reactions, shaft and belt speeds, contact-state sequence, transmitted torque, and any forward/reverse power transfer. The study does not schedule backshift, clamp force, contact states, a target RPM, or engine braking.

The cyclic section represents longitudinal loading through grade. Vertical vehicle dynamics, suspension and tyre contact loss are outside this host.

## Diagnostics and sign conventions

Boundary power is `tau_B,j * omega_j`. CINDER's solved `tau_j` is belt torque on the pulley, so the labelled channel powers are

- `primary_to_belt_power = -tau_p * omega_p`;
- `belt_to_secondary_power = tau_s * omega_s`.

Both positive is labelled forward transmission; both below -1 W is labelled reverse transmission. Mixed signs can accompany storage or small-power conditions and are not forcibly classified. These are shaft torque powers, not a claim that every instantaneous internal contact power equals them during changing stored energy.

Kinetic-slip loss is `-lambda_j N_j v_rel,j` only at contacts declared slipping. Numerical sticking drift is not added as physical loss. Capture energy comes from the actual transition metadata. End state and boundary work remain visible; lower accumulated slip work over unequal duties is not called greater efficiency.

Local normal-loading minima use the released analytical endpoint tensions:

`min(dN_j/dtheta) = (min(T_in,T_out) - q(v_b^2 - r_cm r_cm_ddot))/sin(beta)`.

The reported screening tolerances are diagnostic flags, not new contact laws. No negative load is clipped into an admissible physical state.
