# Local test report — exploratory add-on

## Mechanical release and environment

Tests used the **actual released cinder-cvt 1.1.2 wheel**, SHA256
`f9c454963006d701b33197bdef3be60abebc591199aef7f4b52f37a7159310c3`.
The package was installed, not imported from the live repository. Shared
Results baseline and reference-model Python helpers were checked against the
Git blobs listed in `SOURCES.md`.

The local environment was Linux, Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0,
and Matplotlib 3.10.8. **This is not the exact frozen Results environment**
(Python 3.12 / NumPy 2.5.2 / SciPy 1.18.1 / Matplotlib 3.11.1).
These checks establish execution and internal study-contract behavior, not
cross-environment equivalence, numerical convergence, or experimental validation.
The user should run through the existing release-specific environment. Native
Windows execution was not available here; process-spawn parallelism was tested
on Linux and entry points use the Windows-safe main guard.

## Completed checks

* 20 unit/input tests passed on the final source: course continuity and analytic
  grade derivative; road-distance height mapping; nonextrapolating first passage
  including pauses/rollback; segment-preserving quadrature; every input tune's
  unchanged boundaries, geometry, friction and mechanism; consistent flyweight
  moments; and the complementary helix-angle convention.
* All 32 competitors were constructed and dynamically integrated using process
  isolation on the 420 m, 38-degree / 6 m-wavelength screen course.
  **31 reached the finish; D02 was censored by the slow-progress rule at about
  192.5 m**, after 50 simulated seconds. No inspection errors or sampled
  admissibility review flags appeared in those 32 test outputs.
* A subsequent full-course regression of R00, H18 and D02 reproduced their
  finish/progress categories and maximum distances after review/reporting fixes.
* Four final-source 3 s launch smoke runs (R00, W90, H18, D02) completed the
  requested interval using four spawned worker processes, with no inspection
  failures. `time_limit` is their expected status because the smoke horizon
  intentionally ends before the finish line.
* Repeating that smoke invocation with `--resume` reused all four complete
  outputs. `--prepare-only` resolved to the same campaign fingerprint.
* A deliberately tiny wall-time budget produced `wall_timeout`, no finish time,
  a separately labelled unaccepted trial probe, and a readable report. It was
  not labelled a physical failure to climb.
* Offline report generation was executed; whole-course, regime/shift-event,
  force, ratio, traction and power plots were generated. Representative
  whole-course and event-window plots were rendered and visually inspected.
* Event-ID and attained-distance close-ups executed from saved outputs, without
  integration. Optional course-screen planning generated the six 35/38/40-degree
  and 4/6 m configurations. Those six alternate full fleets have not all been run.
* Source syntax compilation passed. The manifest was checked against the
  repository validator's required envelope and allowed classification values.

## Interpretation of the local outcomes

`local_fleet_test_outcomes.csv` records the 32-car execution check. It is not an
optimized ranking or an approved manuscript dataset. The full fleet was run
before the final report-label, input-validation and runtime-invocation logging
polish; the integration equations and tune/course values were unchanged.
Full-course regression and final-source smoke tests cover those follow-up edits.

The reference run reached high ratio before the hill, backshifted after hill
entry, and showed shift motion through the cyclic section. Several candidates
responded differently. D02 accumulated substantial kinetic-slip work before
meeting the slow-progress rule. These observations nominate useful inspection
windows; they are not automated causal conclusions.

All entrants retained full throttle. The descent could drive the original
engine map into its extrapolated overspeed-resisting tail (reference peak near
5000 rpm in this run). Reverse transfer and engine absorption are therefore
possible without a braking schedule. This is an important scope warning for
interpreting that sector: it is a property of the supplied boundary model,
not a validated CH440 overspeed or closed-throttle prediction.

Work totals use sampled, within-segment trapezoidal diagnostics. Selected claims
need tighter sampling/integration and checkpoint-interval checks before paper
use. The study's 2 s administrative solver restarts preserve state, active
regime and the same CINDER continuation object but restart LSODA's step history.
The pure-rolling road model does not enforce tyre traction, suspension contact,
component-temperature limits, or mechanical damage from prolonged slip.
