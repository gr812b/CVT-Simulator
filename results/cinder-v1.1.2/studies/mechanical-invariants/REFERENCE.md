# CINDER v1.1.2 Mechanical-Invariant Verification Reference

## 1. Verification claim

The purpose of this study is to support a stronger statement than “the reference launch did not obviously break.” CINDER is formulated as an initial-value problem that can begin from arbitrary **admissible** states and move between multiple structural and tangential contact regimes. Mechanical verification should therefore challenge the admissible operating domain directly.

A clean PASS means that a deterministic set of deliberately constructed initial-condition classes and the frozen realistic reference trajectory satisfy the retained mechanical constraints of CINDER 1.1.2. It is broad domain evidence, not a formal proof over the continuum of every possible initial state, load, design, or omitted contact topology.

## 2. Physical admissibility conditions taken from the formulation

While engaged, the prescribed planar belt path assumes a taut flexible belt and continuous wrap contact. That description is admissible only while

- belt tension is nonnegative everywhere around the loop, `T(l) >= 0`;
- distributed wrap normal loading is nonnegative, `dN_j/dtheta >= 0`;
- integrated normal resultants `N_p, N_s` are nonnegative;
- every mounted unilateral mechanism contact carries compression on its selected branch;
- every active metal/support stop carries a nonnegative reaction in its permitted pushing direction;
- sticking contacts satisfy the no-relative-motion constraint and remain within static traction capacity;
- sliding contacts use the kinetic traction magnitude with a direction consistent with relative motion and do non-positive pair work;
- every active geometric/kinematic constraint is satisfied.

Negative tension is interpreted as slack and negative distributed normal loading as local lift-off. A negative helix/ramp contact margin similarly means the selected unilateral mechanism topology would need to pull. These are missing-topology conditions, not physical negative loads to be clipped away.

## 3. Why the tension-field check is exact for this reduced field

CINDER reconstructs four wrap-boundary tensions after the closure solve. Straight-span tension is linear between its endpoints. Each wrap uses the analytical endpoint form

`T(u) = T_in + (T_out - T_in) * expm1(-z u) / expm1(-z)`, `u in [0,1]`,

with the linear limit at `z -> 0`. The interpolation weight is monotone from 0 to 1 for any finite real `z`, so the minimum tension in every region occurs at a region endpoint. Therefore the minimum of the entire reduced tension field is exactly the minimum of the four recovered boundary tensions; no arbitrary spatial mesh is required.

For each wrap the formulation gives

`dN_j/dtheta = [T_j(theta) - q (v_b^2 - r_j,cm * rddot_j)] / sin(beta)`.

The offset term is constant with respect to wrap angle at a frozen state. Since `T_j(theta)` is monotone, the minimum distributed normal loading also occurs at one of the wrap endpoints. The checker additionally analytically integrates the reconstructed tension interpolation and confirms that the resulting normal resultant agrees with the solved `N_j`.

## 4. Geometry-domain audit

The study sweeps the full physical shift range rather than checking geometry only where one trajectory happens to travel. It verifies finite positive operating geometry and engaged fixed-belt-length closure over the complete range. Deadzone and engaged-side geometry are evaluated using their production one-sided maps. In the deadzone, the belt-contact radii must have zero first/second shift derivatives. In the engaged region, the reported first and second radius derivatives are cross-checked against centered finite differences of the independently re-evaluated radius map away from the one-sided boundaries.

This is still primarily a production self-consistency check: the same geometry mapping used by the dynamics is being audited, with finite differences providing a local derivative cross-check. It is not independent experimental validation of the geometric assumptions.

## 5. Shared operating-case ownership

Reusable operating-case and search recipes live in
`../../defaults/verification_operating_cases.json`. The mechanical-invariants
study is the original source of those case classes, but it no longer owns a
private duplicate of their torque, inertia, speed, shift, or contact-branch
search ranges. Other verification studies may consume the same recipes while
applying different diagnostics and pass/fail policies.

This separation is intentional: an *operating case* describes the mechanical
state/load class to challenge, while an *invariant* describes what this study
requires of an accepted state. Changing a numerical guard therefore does not
change the shared scenario, and changing a shared scenario is visible to every
consumer.

## 6. Controlled bench boundaries

The domain cases reuse the decoded frozen Baja CVT plant but replace the realistic engine/vehicle environment with CINDER's existing constant shaft-port boundaries:

`tau_ext,p = constant`, `tau_ext,s = constant`, with prescribed nonnegative referred inertias.

A `NoHost` supplies no additional dynamics. This does **not** modify belt, pulley, actuator, contact, closure, or hybrid physics. It simply prevents the engine curve and road-load model from deciding which initial-condition classes can be visited.

The signed torque pair is searched only to find an admissible example of a requested topology. A topology is never forced to pass: the production classifier must select it, the instantaneous invariant audit must pass, and a short production hybrid continuation must remain admissible.

## 7. Tangential contact coverage matrix

At an interior engaged shift with `sdot = 0`, requested relative speeds are constructed from

`v_rel,p = v_b - r_p,eff * omega_p`,
`v_rel,s = v_b - r_s,eff * omega_s`.

The required cases are:

| Requested class | Primary | Secondary | Purpose |
|---|---|---|---|
| stick-stick forward | stick | stick | fully constrained tangential state |
| stick-stick reverse | stick | stick | overall rotation-sign symmetry |
| primary slip + | `v_rel,p > 0` | stick | primary kinetic direction 1 |
| primary slip - | `v_rel,p < 0` | stick | primary kinetic direction 2 |
| secondary slip + | stick | `v_rel,s > 0` | secondary kinetic direction 1 |
| secondary slip - | stick | `v_rel,s < 0` | secondary kinetic direction 2 |
| both-slip ++ | `>0` | `>0` | quadrant I |
| both-slip +- | `>0` | `<0` | quadrant II |
| both-slip -+ | `<0` | `>0` | quadrant III |
| both-slip -- | `<0` | `<0` | quadrant IV |

A case counts only if the production classifier returns the requested `EngagedContactMode` and stored slip direction(s), the requested branch persists for a resolved nonzero interval above the event-time numerical scale, and the complete short hybrid continuation plus exact successor states satisfy the full invariant audit. A kinetic branch is not required to survive an arbitrary 0.5 ms simply to be considered mechanically real; rapid restick or direction exchange is itself legitimate hybrid behavior when the successor is admissible. Slip-direction requests are searched with both overall rotation signs before being reported missing.

## 8. Structural-regime coverage

The five operating structures are challenged explicitly:

- deadzone lower stop: true zero-speed, zero-external-torque rest state;
- deadzone free: interior deadzone snapshot satisfying the imposed belt-secondary lock;
- engaged low-ratio seat: directed arrival from just above the engagement/seat boundary;
- engaged free shift: supplied by contact-mode cases and the nominal run;
- engaged upper stop: directed arrival from just below maximum shift.

Additional directed boundary cases approach the lower deadzone stop and first engagement so that the event/reset path, not merely an exact constrained snapshot, is exercised. The lower-stop search explicitly includes low and zero shaft speeds because a high primary flyweight speed can physically reverse an opening approach before the lower stop is reached. Two additional interior engaged cases prescribe positive and negative `sdot` and require a short admissible free-shift continuation, so both upshift and backshift coordinate directions are challenged away from the stops. Their zero-relative-motion initialization uses the production representative contact speed, including secondary helical-member motion for nonzero `sdot`. Coverage of the sign of free shift is credited from any audited engaged-free state, including the realistic nominal trajectory; the dedicated bench cases remain stress probes rather than artificial gatekeepers.

## 9. Exact hybrid successor states

Every hybrid transition record with a successor is inspected at the exact post-transition state. This is a hard criterion. A reset is not considered verified merely because the preceding continuous segment was healthy.

The exact terminal point of an outgoing kinetic-slip segment is treated carefully: at a restick or kinetic-direction reversal, relative speed is exactly zero and the outgoing branch may become direction-inconsistent by construction. That endpoint is not counted as an interior slip-direction failure. The exact successor state must still pass independently.

## 10. Static case

The static case uses

`omega_p = omega_s = v_b = sdot = 0`, `tau_ext,p = tau_ext,s = 0`

at the deadzone lower stop. This checks whether the installed spring/mechanism and stop reactions support an actual stationary CVT under the retained model, rather than calling a slowly varying driven state “static.”

## 11. Negative and classifier controls

The checker deliberately supplies states outside the physical shift interval and a deadzone state that violates `v_b = r_s,e omega_s`. Those states must be rejected rather than silently projected into a valid accepted state.

At the exact engagement coordinate the one-sided rule is also checked: opening velocity belongs to deadzone; closing velocity belongs to the engaged side. This verifies an important initial-state classification convention separately from the dynamic event path.

## 12. Hard invariant metrics on every accepted engaged sample

The audit records and checks:

- fixed-belt-length residual;
- full 8x8 affine closure rank and row-scaled equation residual;
- `N_p`, `N_s`;
- exact minimum reconstructed belt tension;
- exact minimum `dN_p/dtheta`, `dN_s/dtheta` under the reduced analytical wrap field;
- reconstructed-normal integral residual against solved `N_p`, `N_s`;
- primary and secondary `lambda`;
- stick velocity drift and acceleration compatibility;
- static traction reserve;
- kinetic slip direction and pair power;
- every generic mounted-element `compressive_contact_margin` exposed by the production actuator API;
- low-ratio, upper-stop, and lower-stop unilateral reactions;
- fixed-shift `sdot`/`sddot` constraints;
- deadzone belt-secondary speed and acceleration locks.

The raw histories remain in CSV form. Headline guard ratios are not the scientific result; the physical values and coverage matrix are.

## 12. Missing-coverage diagnostics

A requested class that cannot be populated is not treated as proof that the class is globally impossible. For every candidate that reaches production classification, the search log retains the observed contact mode, actual relative speeds, solved normal resultants, exact minimum belt tension, exact minimum distributed normal loading, static margins, minimum mechanism margin, and scaled closure residual. Full exception text is retained when classification fails. A small deterministic edge-domain fallback then probes additional low/high shift and speed points, slip magnitudes, both overall rotation signs, and wider signed shaft torques. Only after that search remains empty is the class left as REVIEW for mechanical interpretation.

## 13. PASS / REVIEW / FAIL semantics

**PASS**: every required deterministic coverage class was populated, every accepted sampled state passed the hard checks, exact successor-state inspection passed, and all negative/classifier controls behaved as specified.

**REVIEW**: no hard invariant violation was found, but at least one required coverage class could not be populated by the configured deterministic search. The missing class must be inspected before claiming domain closure. Search ranges may be expanded only with a recorded physical justification; a missing physically impossible class should instead be documented as such.

**FAIL**: an accepted state violates a hard mechanical invariant, an exact successor state is invalid, geometry-domain closure fails, or a negative/classifier control behaves incorrectly.

## 14. What this study does not prove

It does not prove the constitutive assumptions are experimentally true, prove global uniqueness of the nonlinear stick root, prove numerical convergence of the time integrator, or verify unmodeled topologies after a unilateral contact lifts off. Those belong respectively to validation, closure-conditioning, solver-convergence, and future topology extensions. It also does not claim exhaustive continuum coverage of arbitrary real-valued initial conditions; it is a deliberately broad, reproducible domain challenge built around the distinct mechanical classes in the formulation.
