# CINDER v1.1.2 Mechanical-Invariant Verification Reference

## 1. Verification claim

CINDER is an initial-value model that can begin from arbitrary **admissible**
states and move between structural and tangential contact regimes. Mechanical
verification should therefore challenge the retained operating domain directly,
not only show that one Baja launch runs.

A clean PASS means a deterministic set of deliberately constructed state classes,
rare-state reproduction anchors, and the frozen reference trajectory satisfy the
mechanical constraints retained by the v1.1.2 results model. It is broad domain
evidence, not a formal proof over every real-valued state or omitted topology.

## 2. Results reference secondary helix

General v1.1.2 result studies use a zero-clearance **bilateral/slotted**
secondary helix. The results support layer reuses the exact production
`HelicalTorqueReactionForce` equations for signed reacted torque, axial force,
torsional preload, movable-member inertia and shaft reaction. The only change is
that the element does not expose the selected-flank `compressive_contact_margin`.
A sign reversal is therefore reacted by the opposite slot flank.

This is a valid CVT mechanism topology and deliberately prevents a hardware-
specific flank lift-off from terminating studies whose purpose is to stress the
belt/closure formulation. Unilateral-versus-slotted consequences are reserved
for their own topology study.

## 3. Retained physical admissibility

While engaged, the modeled planar belt path assumes a taut flexible belt and
continuous wrap contact. The retained description is admissible only while:

- belt tension is nonnegative everywhere, `T(l) >= 0`;
- distributed wrap normal loading is nonnegative, `dN_j/dtheta >= 0`;
- integrated normal resultants `N_p, N_s` are nonnegative;
- every **retained unilateral** mechanism contact and active travel/support stop
  carries a nonnegative reaction in its pushing direction;
- sticking contacts satisfy no-relative-motion and static traction capacity;
- sliding contacts have Coulomb-consistent direction and non-positive pair work;
- every active geometry/kinematic constraint is satisfied.

The bilateral secondary helix is not included in the unilateral-margin list.
Its signed force still enters the dynamics exactly.

Negative tension means the taut-belt topology would need slack. Negative local
normal loading means the prescribed full wrap would need local lift-off. These
are topology boundaries, not negative physical loads to clip away. Real hardware
may continue through deformation, creep, slack, partial lift-off, altered wrap,
or another omitted topology.

## 4. Exact reduced-field checks

CINDER reconstructs the four wrap-boundary tensions. Straight spans are linear;
each wrap uses the analytical endpoint exponential interpolation. Its weight is
monotone on the wrap, so the exact minimum tension occurs at a boundary.

For each wrap,

`dN_j/dtheta = [T_j(theta) - q (v_b^2 - r_j,cm * rddot_j)] / sin(beta)`.

At a frozen state the radial offset is constant over the wrap, so the minimum
local normal loading occurs at the same minimum-tension endpoint. The checker
also integrates the recovered field and compares it with solved `N_j`.

## 5. Geometry-domain audit

The full physical shift range is swept, including the one-sided deadzone/engaged
tangent at first contact. Fixed belt length, finite positive geometry, deadzone
zero radius derivatives, and engaged radius derivatives are checked over the
whole domain; reported derivatives are cross-checked with independent finite
differences away from one-sided boundaries.

## 6. Shared operating-case ownership

Reusable cases live in
`../../defaults/verification_operating_cases.json`. Search recipes describe state
classes; rare reproduction anchors are fully specified release-scoped states
promoted after the missing-coverage exploration. Neither kind is evidence until
the consuming study's production classifier, invariant audit and hybrid
continuation accept it.

The two rare anchors are `secondary_slip_plus` and `both_slip_mp`. Their purpose
is reproducibility, not to hide that these classes occupy difficult parts of the
retained state space.

## 7. Controlled bench boundaries

Domain cases reuse the decoded reference CVT but replace engine/vehicle behavior
with CINDER's `FixedShaftBoundary` on each shaft and `NoHost`:

`tau_ext,p = constant`, `tau_ext,s = constant`, with prescribed referred inertia.

This changes the environment, not the belt, pulley, closure or hybrid equations.
It lets the invariant study visit state classes that a nominal vehicle launch
would never naturally sample.

## 8. Tangential contact coverage

Required classes are:

| Class | Primary | Secondary |
|---|---|---|
| stick-stick forward/reverse | stick | stick |
| primary slip + / - | slip ± | stick |
| secondary slip + / - | stick | slip ± |
| both-slip ++ | + | + |
| both-slip +- | + | - |
| both-slip -+ | - | + |
| both-slip -- | - | - |

A class counts only if the production classifier returns the requested topology
and direction(s), the branch persists for a resolved nonzero interval above the
event-time scale, the complete hybrid continuation is healthy, and exact
successor states pass. A kinetic branch is **not** required to live for an
arbitrary dwell time: rapid restick/direction exchange is legitimate dynamics.

Targeted anchors are tried first only for the two rare classes. If an anchor no
longer passes, the ordinary standard/extended deterministic search still runs.

## 9. Structural coverage

The study explicitly exercises:

- true zero-speed, zero-external-torque deadzone lower-stop rest;
- free deadzone with the belt-secondary lock;
- first engagement and engaged low-ratio-seat arrival;
- engaged free shift with positive and negative `sdot`;
- upper-stop arrival;
- lower-stop arrival from free deadzone;
- forward and reverse overall rotation.

For nonzero `sdot`, tangential compatibility uses CINDER's production
representative-contact-speed definition, including helix member motion.

## 10. Exact hybrid successors

Every transition record with a successor is inspected at the exact post-reset
state. The exact terminal point of an outgoing slip segment may be direction-
inconsistent by construction at a zero-speed event; that outgoing endpoint is
not treated as an interior kinetic-direction failure, but the exact successor is
always audited independently.

## 11. Static and negative controls

The static case uses zero shaft speeds, zero belt speed, zero shift speed and
zero external shaft torques at the deadzone lower stop. Invalid shift-domain
states and a deadzone state that violates the belt-secondary lock must be
rejected, not projected into an accepted state. Engagement-side classifier
controls separately check the one-sided opening/closing rule at the exact
engagement coordinate.

## 12. Hard metrics on accepted samples

The audit records/checks fixed-belt-length residual, rank/scaled residual of the
8x8 affine closure, normal resultants, exact minimum recovered tension, exact
minimum local distributed normal loading, field-normal integral residual,
traction utilization, stick residuals/static reserve, kinetic direction/pair
power, retained unilateral mechanism margins, stop reactions, fixed-shift
constraints, and deadzone belt lock.

The physical values are the scientific evidence; numerical guard ratios are only
reporting thresholds.

## 13. PASS / REVIEW / FAIL

**PASS**: every required deterministic class is populated, every accepted sample
and exact successor passes, geometry/static checks pass, and negative/classifier
controls behave correctly.

**REVIEW**: no accepted state violates a hard invariant, but a required class is
not reproducibly populated.

**FAIL**: an accepted state violates a retained mechanical invariant, an exact
successor is inadmissible, geometry closure fails, or a negative/classifier
control behaves incorrectly.

## 14. Capability interpretation beyond PASS

Coverage alone does not say how large a regime's admissible neighbourhood is.
The companion `CAPABILITY_INTERPRETATION.md` therefore separates:

1. branch-equation admissibility;
2. production-classifier retention of that topology;
3. branch dwell / first exit event; and
4. the first violated physical inequality in neighbouring states.

The working assumption-to-consequence map focuses on the single global belt
transport coordinate, fixed length/no longitudinal strain, taut belt,
prescribed continuous wraps, one gross traction state per wrap, and the
representative secondary contact reduction. Those are the assumptions expected
to make unusual opposing-slip/secondary-slip states narrow even though the gross
regime itself is valid.

## 15. What this study does not prove

It does not prove constitutive assumptions experimentally, prove global
uniqueness of the nonlinear stick root, prove time-integrator convergence, or
model continuation after belt slack/partial wrap separation. Those belong to
validation, closure-conditioning, solver-convergence, and future topology
extensions. Nor does it claim that a state inadmissible under the retained
belt/contact topology is impossible in real hardware.
