# Diagnosis of the corrected-friction low-ratio closure singularity

## Status

The singular closure reported by the v9 Ballew benchmark was an implementation
error at the deadzone/engagement geometry kink. It was **not** a singularity of
the intended CINDER free-shift equations and was **not** repaired by changing
friction, actuation, inertia, belt mechanics, or any Ballew parameter.

The corrected implementation gives the active engaged regime its right-hand
(one-sided) geometry derivatives at the shared engagement / low-ratio boundary.
The deadzone evaluator retains the deadzone-side derivatives. Geometry values
remain continuous and unchanged.

## Reproduced failing stage

With Ballew's published friction values translated into CINDER's traction
convention (A10), the force-replay case approached the low-ratio seat while in
free both-slip contact. The last safely integrated state was approximately

- `t = 0.03225186 s`;
- `s = 0.5 um`;
- `s_dot = -2.655 m/s`.

During LSODA's normal event bracketing, an internal trial stage was evaluated at

- `t = 0.0322810525 s`;
- raw `s = -76.831 um`;
- `s_dot = -2.6428 m/s`.

The raw state is intentionally retained for the low-ratio event function. The
engaged evaluator separately projects only the geometry used by that rejected
trial stage to the nearest legal point, `s = 0`.

## Why the old matrix became exactly singular

`BeltPulleyGeometry` historically used the rule

```python
if shift <= deadzone_shift:
    dr_p_ds = 0
```

and applied the same deadzone-side branch to the representative belt axial
coordinate. Ballew's Chapter 5 reconstruction has a zero-width deadzone,
`deadzone_shift = 0`. Therefore the projected engaged trial at exactly `s = 0`
was assigned the deadzone-side kinematics

- `dr_p/ds = 0`;
- `dr_s/ds = 0`;
- `dx_b/ds = 0`.

That is not the engaged-side limit. Immediately inside the physical engaged
domain the same geometry has approximately

- `dr_p/ds = +1.8660254`;
- `dr_s/ds = -1.42839`;
- `dx_b/ds = 0.5`.

For the Ballew reconstruction the two literal moving-sheave axial masses are
zero. Consequently the primary and secondary local clamp rows algebraically
set `N_p` and `N_s`; they do not contain `s_ddot`. In free shift, the only
remaining direct `s_ddot` coefficient is in CINDER's reduced closed tension-loop
row through

`r_ddot = r'(s) s_ddot + r''(s) s_dot^2`.

When both pulley radius derivatives were incorrectly set to zero, the entire
`s_ddot` column of the 8x8 free both-slip matrix became zero. The reproduced
matrix had

- rank `7`;
- determinant `0`;
- condition number about `2.43e18`;
- exact right null direction proportional to
  `[0, 0, 0, -1, 0, 0, 0, 0]`.

Thus the solver was correctly reporting that `s_ddot` had become mathematically
undetermined in the assembled matrix. The cause was the wrong branch derivative,
not missing physical force information.

## Architectural correction

A hybrid boundary can be continuous in position while having different
one-sided derivatives in its adjacent regimes. The geometry API now makes that
explicit:

- `geometry.evaluate(s)` retains the historical deadzone-side derivative
  convention at `s == s_engage`;
- `geometry.evaluate_engaged(s)` returns the identical positions/radii but the
  engaged-side derivatives at `s == s_engage`;
- `MechanicalCVTPlant.snapshot_at_time(...)`, which builds the engaged/contact
  snapshot, uses `evaluate_engaged`;
- the separate deadzone snapshot continues to use `evaluate`.

This avoids an epsilon / `nextafter` workaround and assigns the derivative by
physical regime, which is the appropriate treatment of the piecewise-smooth
coordinate.

During event localization an engaged trial stage that falls just outside the
legal shift interval is still projected to the boundary for geometry only, but
it now keeps the **engaged-side** derivative there. The raw shift remains
unchanged for the event function, so the physical stop is still localized at
`s = 0`.

## Before/after check at the exact previously failing trial state

Using the same time, raw state, both-slip directions, shaft boundaries, clamp
forces, and translated kinetic traction magnitude:

**Before**

- rank `7`;
- `cond(A) ~= 2.43e18`;
- tension-loop `s_ddot` coefficient `0`;
- solve fails as singular.

**After**

- rank `8`;
- `cond(A) ~= 5.38e3` in the unscaled mixed-unit matrix;
- tension-loop `s_ddot` coefficient `-0.41875`;
- finite closure solution, including `s_ddot ~= 424.6 m/s^2`.

The raw condition number should not be interpreted as a dimensionless physical
conditioning metric because the matrix mixes units and scales. The decisive
checks here are restoration of full rank and the exact disappearance of the
`s_ddot` null direction.

## Integration checks

After the one-sided-geometry correction:

- the force-replay case passes the previous failure and localizes the low-ratio
  event at `t ~= 0.03225205 s`;
- it integrates through repeated low-ratio and high-ratio stop encounters to at
  least `1.0 s` under the benchmark tolerances;
- the reconstructed PI-controller case also passes its previous `~17.2 ms`
  failure and integrates to at least `1.0 s`;
- focused geometry / zero-width-deadzone / contact-switch regression tests pass.

The later violent shift behavior is still a **model-comparison result**. This fix
only makes CINDER evaluate its existing engaged equations consistently at the
hybrid boundary; it does not make CINDER behave more like Ballew.

## Why this matters outside Ballew

Ballew's zero sheave masses made the bug become an exact rank deficiency, so it
was easy to see. With nonzero moving-sheave mass, another axial row can retain an
`s_ddot` coefficient and mask the singularity. Such a case could remain solvable
while still using the wrong deadzone-side `dr/ds` at an engaged boundary.
Therefore one-sided regime-aware geometry is the more general correction.

## Second hybrid-boundary issue found by the full closed-loop run

The first boundary correction restored the correct engaged-side geometry derivatives and removed
an exact matrix singularity. A subsequent full closed-loop run exposed a separate unilateral-
constraint bookkeeping defect.

At a low-ratio seat or upper stop, CINDER monitors the recovered unilateral reaction as a terminal
event. That is sufficient while the contact topology stays fixed. However, a discrete stick/slip
transition can instantaneously change the closure solution and therefore jump the recovered stop
reaction across zero without any continuous crossing occurring inside either adjacent ODE segment.

The Ballew controller case demonstrated this concretely. At the second low-ratio-seat encounter:

- the seat was entered at `t = 0.0394258311 s` with a compressive/admissible reaction of about
  `+815.19 N`;
- at `t = 0.0423149471 s` the secondary contact re-stuck;
- evaluating the **successor contact branch at the same state** gave a low-ratio-seat reaction of
  about `-75.89 N`.

The old transition resolver retained the `LOW_RATIO_SEAT` shift constraint because the event that
fired was a contact event rather than `LOW_RATIO_SEAT_RELEASE`. The next segment therefore began
already on the tensile/inadmissible side of the release event. Since the release event was configured
to detect a positive-to-negative crossing, no later crossing was guaranteed and the state could be
artificially trapped at the seat.

### Architectural correction

After every contact-topology transition while a unilateral shift constraint is active, the successor
contact branch is now evaluated immediately at the event state:

- if a low-ratio seat would require a negative/tensile closing reaction, the successor mode is changed
  to free engaged shift at the same event time;
- if an upper stop would require a negative/tensile opening reaction, it is likewise released;
- otherwise the contact transition proceeds with the existing shift constraint.

This is a hybrid admissibility correction, not a change to any force law. It simply guarantees that a
new ODE segment cannot start with a unilateral constraint that the newly selected contact branch
cannot physically support.

Focused tests cover low-seat release, low-seat retention, and upper-stop release after contact-mode
changes. Together with the zero-width-deadzone, one-sided-geometry, and zero-crossing tests, the
focused regression set passes.

After this correction the Ballew cases exhibit many more legitimate seat/stop releases and impacts.
The benchmark transition safety limit was therefore raised from 200 to 2000; the limit is purely a
runaway-event guard and does not alter the model equations or event locations.
