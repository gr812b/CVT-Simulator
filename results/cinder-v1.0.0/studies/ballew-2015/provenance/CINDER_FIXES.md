# CINDER changes exposed by the Ballew reconstruction

The Ballew benchmark was unusually useful as a stress case because its
zero-width deadzone, zero moving-sheave masses and dense contact switching made
implementation defects become obvious. These corrections are already part of
the frozen `cinder-v1.0.0` mechanics; they are **not study-local patches** and
must not be re-applied by the results code.

The exact historical diagnostic document is copied by `migrate_legacy.py` to
`provenance/legacy-docs/SINGULARITY_DIAGNOSIS.md`, and the exact legacy benchmark
code is preserved under `provenance/legacy-code/`.

## 1. Regime-aware one-sided geometry derivatives at engagement

### Failure

The corrected-friction force-replay run localized near the shared engagement /
low-ratio boundary. Historically, geometry evaluation at
`shift == deadzone_shift` selected the deadzone side, giving zero radius and belt
axial derivatives even though the active mode was engaged.

The Ballew case has:

- zero-width deadzone (`deadzone_shift = 0`);
- zero primary and secondary moving-sheave masses.

At the engaged trial projected to `s=0`, the old evaluator therefore supplied
`dr_p/ds = dr_s/ds = 0`. With zero sheave masses, the local clamp rows were
algebraic and no longer supplied an `s_ddot` coefficient. The reduced closed
belt/tension row was then the last direct source of that coefficient, so the
wrong zero radius derivatives made the entire `s_ddot` column of the 8x8 free
both-slip closure matrix vanish. The matrix became exactly rank 7.

### Correction

The geometry API now distinguishes the one-sided derivative by active regime:

- the ordinary/deadzone evaluator retains deadzone-side derivatives at the kink;
- the engaged evaluator uses the right-hand engaged derivatives at the same
  continuous geometric position;
- engaged mechanical snapshots use the engaged evaluator;
- deadzone snapshots retain the deadzone evaluator.

This is a piecewise-smooth coordinate correction, not an epsilon/`nextafter`
workaround and not a change to any Ballew parameter.

The legacy diagnosis reports the previously failing matrix improving from rank 7
and exact singularity to rank 8, with the missing tension-loop `s_ddot`
coefficient restored.

Frozen source location: `cvtModel/src/cinder/model/cvt/geometry/belt_pulley.py`
and the engaged mechanical snapshot path in the v1.0.0 plant.

## 2. Immediate unilateral-stop release after contact topology changes

### Failure

A low-ratio seat or upper stop is unilateral: it may push but may not pull.
CINDER already monitored the recovered stop reaction as a continuous terminal
event. A discrete stick/slip transition, however, can instantaneously change the
closure solution and jump that reaction from compressive to tensile without a
continuous zero crossing inside either neighboring ODE segment.

The Ballew closed-loop case exposed exactly this: a contact re-stick at a
low-ratio seat changed the successor branch's seat reaction from admissible
compression to an inadmissible tensile value. The old resolver retained the
seat merely because the event that fired was a contact event.

### Correction

Whenever contact topology changes while a unilateral shift constraint is active,
the successor contact branch is evaluated immediately at the same event state.
If retaining the stop would require a tensile reaction, the stop is released at
the same event time. Otherwise it remains constrained.

This is hybrid admissibility bookkeeping. It changes no force law, no physical
parameter, and no event location.

The Ballew benchmark consequently exercises many legitimate stop impacts and
releases; its benchmark safety cap was raised from 200 to 2000 transitions only
as a runaway guard.

## 3. Complete successor search at kinetic slip zero crossings

Ballew's finite `0.02 m/s` near-zero friction rule is not copied into CINDER.
Instead CINDER's hybrid contact graph must remain mechanically closed at a
kinetic relative-speed zero crossing.

The v1.0.0 transition logic tries, in order, physically admissible successors
such as re-stick and direction-consistent kinetic continuation. Where an
ordinary one-contact successor is unavailable, the resolver also considers the
simultaneous complementarity exchange in which the zero-crossing contact sticks
while the previously sticking contact releases. Broader both-slip candidates
are diagnostic fallbacks only after the more constrained mixed exchange is
considered. Every candidate remains subject to closure, normal-force,
static-capacity and outgoing-direction admissibility.

This closes a missing topology path; it is not Ballew-specific calibration.

## What the results study should do with these fixes

Nothing special. The results environment must install exactly
`cinder-cvt==1.0.0`; that package already contains the corrections. The Ballew
study should not vendor alternate CINDER mechanics or insert `cvtModel/src` onto
`sys.path`.

The migrated study therefore:

1. verifies the clean 1.0.0 environment;
2. retains the old diagnostics and exact legacy implementation as provenance;
3. runs the cleaned comparison against the released wheel;
4. regression-compares the new run against the historical v1.0.0 outputs.
