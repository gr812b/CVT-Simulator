# Shift-curve shape: spring-rate and ramp-profile exploration

## Install and run

This is an **additive extension to the consolidated `studies/course-tuning/`**
package. Merge the ZIP's `studies/` folder into `results/cinder-v1.1.2`.
No existing file, final input, final runner, or previous artifact is replaced.
It needs the consolidated package and the existing shared Results defaults.

From `results/cinder-v1.1.2`, with its CINDER 1.1.2 environment activated:

```bash
# Optional: tests and full-travel geometry checks; does not integrate trajectories.
python studies/course-tuning/exploration/scans/scan_shift_shapes.py --verify

# All 15 entrants, the same complete 732 m road, final tight numerical settings.
python studies/course-tuning/exploration/scans/scan_shift_shapes.py --jobs 4 --resume --pack
```

This runs **12 new physical candidates plus R00, W85, and W115 controls**.
Every entrant starts from the original common initial conditions. The course is
read from the final study's `inputs/course.json` and checked against its selection
lock. It is not modified or copied into a different course experiment.

Outputs are under:

```text
studies/course-tuning/exploration/artifacts/shift_shape_v1__tight__<fingerprint>/
```

Open **`index.html`** for the familiar full-course report and its prominent
**`shift_shape.html`** link. The latter has the spring/ramp maps and clean
launch-curve slope/shape comparisons. `--pack` makes the sibling
**`shift_shape_v1__tight__<fingerprint>_return.zip`** to send back.

Nothing is automatically promoted into the final fleet. Root `run.py` still
runs the accepted 12 trajectories. Adding or editing this exploration does not
change the root final-run cache identity.

## Why these comparisons

The original mass and preload variations mainly test operating-speed and
clamping changes. This exploration asks whether the **variation of clamping
with travel** can produce a meaningfully different primary-RPM versus
secondary-RPM curve, rather than just move it vertically.

The word “slope” below always means primary RPM on the vertical axis versus
secondary RPM on the horizontal axis, during the specified opening-flat free
upshift. It is not a slope fitted through the entire looping course trajectory.

### Candidate family

All scales refer to the selected Baja baseline.

| IDs | Physical change | Matching policy |
|---|---|---|
| R00 | Unchanged reference | None |
| W85, W115 | Original 85% / 115% replaceable tip mass controls | Original mass-moment updates; no new adjustment |
| P050, P200, P300 | Primary axial spring stiffness 0.5x / 2x / 3x | Match return-spring force at the engagement geometry by changing installed compression |
| S050, S200 | Secondary axial spring stiffness 0.5x / 2x | Match initial secondary spring closing force |
| T067, T150 | Secondary torsional stiffness 2/3x / 1.5x | Match initial torsional spring torque |
| RC10, RC28 | Unchanged first 10 mm of the ramp, then a 5 mm C3 blend and a circular tail ending at 10° / 28° | No mass or spring adjustment |
| RL30 | Same 10 mm unchanged prefix and 5 mm C3 blend, then a straight 30° tail | No mass or spring adjustment |
| RC35L, RC40L | Preserve the first 18 mm, blend over 5 mm, then a circular tail ending at 35° / 40° | No mass or spring adjustment; later onset of profile change |

The reference ramp is a 5 mm straight 35° segment, 3 mm derivative-matched
transition, and 30 mm circular 35°→20° segment. New profiles retain its **38 mm span in
the ramp-profile coordinate**, pivot, arm, roller, reference location, and full
sheave travel. “Tail angle” is specified at the physical ramp endpoint. The
profile distances are coordinate spans, not arc length or sheave displacement. The
roller may not traverse that entire tail during the CVT's stroke; its actual
contact coordinate versus shift is saved explicitly.

These are engineering input comparisons, not a claim that these exact springs
are commercially available, that installed compression is mechanically
packageable, or that a proposed ramp has passed strength/manufacturing checks.
No added spring or ramp mass is invented; the existing ideal spring and rigid
geometry assumptions are retained.

## The preload compensation is explicit

Simply changing stiffness at unchanged installed compression also changes the
initial force. To isolate a force-gradient effect more cleanly, the rate
candidates use a declared one-point match.

For the released axial spring,

```text
compression = c + a*x
F_x = -k * (c + a*x) * a
```

and a stiffness scale `q`, set

```text
k_new = q*k_reference
c_new = (c_reference + a*x_anchor)/q - a*x_anchor.
```

The primary anchor is `x_p = s_deadzone = 0.0024892 m`; the secondary anchor is
`x_s = 0`. Thus the spring force is preserved at the low-ratio engagement
geometry, not everywhere. The primary matched force is not a prescribed
engagement RPM or a forced dynamic state.

For the torsional spring, `k_theta_new = q*k_theta` and
`theta_preload_new = theta_preload/q`, preserving the torque at `theta=0`.
The helix profile, torque share and movable-member inertia are unchanged.

The exact new rates, installed compressions, twist values, matching residuals,
and every changed document field appear in `competitors_resolved.csv` and each
`cases/<ID>/resolved_case.json`. There is no hidden mass or primary-preload
recalibration for the ramp candidates.

## Ramps are physical geometry, not an imposed force curve

The new nose/prefix is cut from the original profile without changing its
geometry. The connecting segment is built with CINDER 1.1.2's own
`C3TransitionSegment.between_segments`, using both neighbors' first, second,
and third derivatives. CINDER then rebuilds and validates the complete
fixed-pivot roller-contact branch over the full declared sheave stroke.

The full dynamic flyweight law receives the new `q(x)`, its derivatives and
mass-dependent inertia maps normally. We do not multiply the existing
centrifugal force, retain a stale inertia map, prescribe an RPM trace, clip
travel, relax geometry checks or swap to quasi-static mechanics.

An early 40° tail was rejected during development because the original roller
could not follow it over the full required stroke. A 32° early circular tail
also triggered the physical double-contact check. Those rejected drafts were
not made runnable by weakening a test; the supplied five profiles passed the
released geometry audit. Their development checks are recorded in the test
report, not included as misleading vehicle competitors.

All entrants retain:

- the original full-throttle engine and locked-final-drive vehicle boundaries;
- the same 732 m course, initial conditions and observation/rollback rules;
- full dynamic fixed-pivot flyweights and the dynamic bilateral/slotted helix;
- the same belt, contact coefficients, literal sheave masses, fixed hardware
  inertias, final drive and vehicle;
- the same primary mass moments for all new rate/ramp candidates.

R00/W85/W115 are unchanged comparison controls. The final study remains locked
and separate.

## What the new report measures

### Full histories

The existing per-car, family, overall and phase-coloured shift plots are
retained, along with event records, powers, forces, contact margins, regimes,
course-sector performance and raw data. The complete course is simulated so a
visually attractive launch curve cannot hide a poor hill or cyclic response.

### Shape-specific views

The cleaner slope analysis uses the **opening flat only**, stops at its first
exit, and retains only engaged, **free-shift, stick–stick**, positive-shift-rate
motion with increasing secondary RPM in **15–85% active shift travel**.

It excludes clutch slip, the low-ratio seat, upper-stop dwell, backshifting,
later hills and descent. It never sorts a whole-course loop into a single-valued
curve. Disconnected valid intervals remain disconnected; physical reset states
are not joined. Equal administrative-checkpoint endpoints can be joined.

The additional figures/tables give:

1. Primary versus secondary RPM over those eligible intervals, by family and
   overall, plus a reference comparison for each car.
2. Early (20–50%), late (50–80%) and overall (20–80%) secant slopes, only if one
   connected eligible path spans both endpoints. These are reported as primary
   RPM change per **1,000 secondary RPM**.
3. Local secants over a 200-secondary-RPM window. These are finite differences
   of the plotted path, not noisy time differentiation or an instantaneous
   force-law derivative.
4. Candidate-minus-R00 primary RPM at matched secondary RPM, followed by removal
   of **one constant mean RPM offset**. The remaining RMS and peak-to-peak
   difference quantify shape change rather than vertical translation.
5. Actual ramp profiles/tangent angles, the centrifugal contribution at a common
   3,000 RPM, reflected flyweight shift inertia, roller contact position, and
   primary/secondary spring maps.

The offset comparison uses the longest connected common secondary-speed domain
on a 401-point grid and **does not extrapolate**. Each pair's domain is saved;
less than 300 RPM overlap is flagged as too narrow for ranking. Missing 20%/80%
coverage or a disrupted sticking interval is explicit, not filled in. Pairwise
shape scores with different supports must not be read as one universal ranking.

A different slope is not automatically a better tune. These are descriptors of
finite transient trajectories, not measured CVT maps, steady-state laws, proof
of damping, or optimization objectives. The goal is to identify informative
candidates and then examine their whole-course consequences.

## Other commands

```bash
# Show all candidate intentions without simulation.
python studies/course-tuning/exploration/scans/scan_shift_shapes.py --list

# Run only the spring family or only selected ramps. R00 is always included.
python studies/course-tuning/exploration/scans/scan_shift_shapes.py --cars primary_rate --jobs 4 --resume --pack
python studies/course-tuning/exploration/scans/scan_shift_shapes.py --cars RC10 RC28 RL30 --jobs 4 --resume --pack

# Three-second plumbing check; time_limit is expected, not a failed car.
python studies/course-tuning/exploration/scans/scan_shift_shapes.py --preset smoke --jobs 4 --cars P200 RC10

# Write resolved documents and hashes without integrating.
python studies/course-tuning/exploration/scans/scan_shift_shapes.py --prepare-only

# Regenerate plots/metrics from an existing shape campaign; no CINDER solves.
python studies/course-tuning/exploration/scans/scan_shift_shapes.py --report-only PATH_TO_CAMPAIGN --pack
```

`--resume` verifies file hashes before reusing completed cases. Incomplete,
damaged or retried outputs are moved to a `previous_attempts/` subdirectory,
not deleted. `--retry-errors` requests rerunning cached setup/integration errors;
physical rollback/progress/time outcomes are not retried into successes.
Each campaign has a lock to prevent concurrent writers. Completed individual
cases survive interruption. Return ZIPs exclude previous attempts and locks.

The default numerical settings are the existing tight preset: LSODA,
`rtol=3e-5`, `atol=3e-8`, `max_step=0.005 s`, 5 ms diagnostic sampling, 180 s
observation limit, and the existing 2 s administrative checkpoints. Alternative
presets and `--max-time` create separate, explicitly fingerprinted campaigns.
Only `--report-only` operates directly on a specified existing campaign.

The selected inputs, source, shared helper hashes and environment are captured
under `provenance/`. All additions live inside `exploration/`; the new runner
never writes final inputs or final outputs.
