# Common-course CVT tuning exploration

A 32-entrant, full-throttle comparison on a **single distance-based course**. Each entrant inherits the Baja reference vehicle and the same complete CINDER mechanics. Only its declared CVT tuning parameters change.

The scientific questions are where a tune gains or loses progress, what happened to the engine/shift/contact response there, and which internal forces or constraints explain the difference. Entrants have motivated *intentions*, not predetermined rankings. This is a discovery study, not an optimizer or a frozen manuscript result.

## Install and run

Extract the ZIP **inside `results/cinder-v1.1.2`**. It adds only:

```text
studies/course-tuning-exploration/
```

Activate the existing CINDER 1.1.2 Results environment. No extra dependency is required beyond that environment. The scripts run against the installed `cinder-cvt==1.1.2` wheel, never a live `cvtModel/src` checkout. The shared `defaults/reference_model` decoder must be present on your current Results branch.

From `results/cinder-v1.1.2`:

```powershell
# Input/unit checks and an installed-release check
python studies/course-tuning-exploration/verify_study.py

# A 3 s launch smoke test; "time_limit" is the EXPECTED result, not vehicle failure
python studies/course-tuning-exploration/run.py --preset smoke --cars R00 W90 H18 D03 --jobs 4

# Full 32-car exploratory comparison
python studies/course-tuning-exploration/run.py --preset screen --jobs 4 --resume
```

`--jobs` uses separate processes, so LSODA is not shared between threads. Start with 2–4 workers; the default is 1. More workers can increase memory use and setup contention. The runner prints its campaign directory and the path to an **offline `index.html` report**. All data are CSV/JSON/NPZ alongside the figures.

Running from repository root also works; prefix the script path with `results/cinder-v1.1.2/`.

```powershell
# See the complete set of intentions, without simulating
python studies/course-tuning-exploration/run.py --list

# Resolve documents and inspect exactly what will change, without simulating
python studies/course-tuning-exploration/run.py --prepare-only

# Follow one family, or a few named candidates
python studies/course-tuning-exploration/run.py --cars reference flyweight --jobs 4 --resume
python studies/course-tuning-exploration/run.py --cars R00 B01 B02 D03 --jobs 4 --resume

# A tighter run of selected candidates; it has its own output fingerprint
python studies/course-tuning-exploration/run.py --preset tight --cars R00 B01 B02 --jobs 3

# Longer observation of a difficult case, without slow-progress censoring
python studies/course-tuning-exploration/run.py --cars D03 --max-time 240 --no-progress-stop
```

The unchanged full-throttle engine map includes its original low/high-speed torque extensions. There is **no throttle cut, imposed braking torque, engine-torque scaling, or scheduled power reversal**. Negative engine power or reverse transmission power, if observed, comes from the original model response and is reported explicitly.

## Starting course

`inputs/course.json` is the initial **exploratory** road, with 420 m of travelled road length:

| Distance (m) | Sector |
|---:|---|
| 0–120 | Flat launch, upshift and high-ratio approach |
| 120–132 | Smooth rise to 38° |
| 132–212 | Sustained 38° climb |
| 212–224 | Smooth return to level |
| 224–264 | Level recovery |
| 264–300 | Six 6 m cyclic grade periods, ±12° peak with smooth end envelope |
| 300–312 | Short level link |
| 312–324 | Smooth transition to −22° |
| 324–384 | Sustained descent |
| 384–396 | Smooth return to level |
| 396–420 | Final level sector |

Transitions use a quintic smoothstep. The cyclic grade is a sinusoid multiplied by a smooth entry/exit envelope. The derivative `dgamma/dx` is analytic and the realized `dgamma/dt = v dgamma/dx` is saved. Frequency is an outcome: in the cyclic sector it is `abs(v)/wavelength`, not a common time-forcing frequency.

The 80 m plateau makes this a sustained climb rather than a short crest that every tune might cross on entry kinetic energy. It is not guaranteed to stop a particular entrant; that is a result to inspect. The 35° and 40° alternatives have the same remaining geometry. The optional course-screen tool writes/executes separate campaigns; it never changes the road for individual cars.

```powershell
python studies/course-tuning-exploration/run.py --course studies/course-tuning-exploration/inputs/course_40deg.json --cars R00 B01 D02 D03 --jobs 4
```

The road coordinate is signed distance **along** the road, consistent with the packaged locked final drive. The elevation sketch integrates `sin(gamma)` with respect to that distance. These are rolling-grade load variations: no suspension, wheel unloading, airborne motion, tyre traction limit or jump impact is added. A prediction of climbing a steep grade is conditional on that pure-rolling/permanent-contact vehicle model.

## Competitors

`inputs/competitors.json` is the editable fleet, with one rationale per car.

| Family | IDs | Difference from R00 |
|---|---|---|
| Reference | R00 | No tuning edits |
| Flyweight hardware | W85, W90, W95, W105, W110, W115 | Concentrated tip mass 85–115% of the reference 250 g per flyweight |
| Primary spring preload | P90, P95, P105, P110 | Initial primary spring compression 90–110% |
| Helix | H16, H18, H22, H25, H28 | Same constant-angle helix, 16–28° from the circumferential direction; same radius |
| Secondary torsional preload | T240, T270, T330, T360 | Initial twist, in degrees |
| Secondary axial preload | C85, C115, C130 | Initial secondary axial-spring compression 85–130% |
| Combined candidates | B01–B06 | Several explicitly motivated combinations |
| Adverse controls | D01–D03 | Premature-shift, late-engagement and weak-secondary hypotheses |

The model remains **dynamic fixed-pivot flyweights and a dynamic bilateral/slotted secondary** for every entrant. The primary ramp, pulley geometry, friction coefficients, belt properties, spring rates, helix radius, literal sheave masses, torque share, vehicle parameters, final drive and shaft-boundary inertias are unchanged. No quasi-static actuator is substituted.

Flyweight mass changes alter the total mass, first moment and second moment consistently at the existing roller-centre station; they are not scalar force multipliers. The fixed shaft inertia is not incremented again. The reference arm moments remain. Total vehicle mass is held fixed as part of the common vehicle boundary; this study ignores the small change in vehicle translational mass from swapping tip hardware.

A helix tune is entered in the manuscript's circumferential convention. The serialized profile uses the complementary angle: the code handles that conversion. No primary-preload retuning is silently used to restore engagement RPM. The combinations explicitly list any compensation.

These are mechanically motivated simulation inputs, not verified available spring parts or certified hardware designs. Coil bind, spring stress, packaging and allowable component speeds are not additional models here.

## Outputs and how to use them

Each campaign is named from the course, solver preset and a fingerprint of the source code, fleet, course, numerical controls, shared inputs/helpers and environment. It contains:

* `index.html`, `leaderboard.csv`, `sector_comparison.csv`, `time_gaps.csv`: progress, sector times and diagnostic comparisons.
* `competitors_resolved.csv`, `campaign.json`, `invocations.json`, `course_profile.csv`: the declared experiment, physical edits and provenance.
* `cases/<ID>/diagnostics.csv`: shaft/vehicle/belt speeds, both ratio definitions, shift rate/acceleration, contact state, normal/tension margins, actuation components, signed powers, slip powers and realized cyclic frequency.
* `cases/<ID>/events.json` and `.csv`: exact event time/distance, previous/next regime, pre/post state, velocity jump, capture loss and CINDER metadata.
* `cases/<ID>/event_windows.csv`, `interesting_windows.csv`: surrounding samples and candidate windows for inspection. These nominate phenomena; they do not automatically infer causes.
* `cases/<ID>/mechanism_map.csv`: flyweight inertia/centrifugal coefficient and helix motion-ratio/reflected-inertia maps.
* `checkpoint_*.npz`, `segment_*.npz`: accepted native solver states and segment-preserving sampled states. Missing intervals are never replaced by fabricated motion.

The HTML shows a selected group and separates families to avoid 32-line spaghetti. Regenerate it with any focus set, **without re-running**:

```powershell
python studies/course-tuning-exploration/analysis/report.py PATH_TO_CAMPAIGN --focus R00 W90 H18 C115 B01 D03
```

When R00 does not reach the later sectors, its time gaps there are undefined. Choose a different comparator with `--reference B01` rather than extrapolate a nonexistent R00 finish. Sector times distinguish an inherited lead from a gain within the sector.

`--no-plots` postpones graphics but still writes the tables and report. Saved raw and diagnostic data remain available for new plot designs.

## Outcome categories

| Status | Meaning |
|---|---|
| `finished` | Located the common finish-distance event |
| `rollback` | Backwards vehicle speed reached −0.25 m/s; a study stop, not a claim that recovery is impossible |
| `progress_limited` | Less than 0.25 m of new forward progress over at least 15 s, checked after 20 s; a censoring rule, not proof of a stalled equilibrium |
| `time_limit` | Reached the common maximum observation time before the finish |
| `model_domain_stop` | CINDER explicitly terminated its modeled regime |
| `integration_error` | Numerical exception/transition budget; not labelled as physical inability to climb |
| `wall_timeout` | Study integration wall-time budget reached |
| `setup_error` | Assembly or initial-state construction failed |
| `worker_error` | Worker or post-processing failed; partial files require inspection |

An additional `review_required` flag marks failed interior post-processing or sampled negative belt/contact/remaining one-sided mechanism margins. A finished trajectory with a review flag should not be treated as a clean competitive result. Exact outgoing event endpoints may need different interpretation from interior kinetic samples, so both counts are retained.

No finishing time is assigned to an incomplete car. No time or speed curve is extrapolated beyond attained distance. The `last_trial_probe_NOT_ACCEPTED.json` file, when present, is **explicitly an ODE trial**, not a physical trajectory endpoint. Useful partial output comes only from successfully returned solver checkpoints.

## Numerical controls

| Preset | rtol | atol | Maximum step | Maximum simulated time | Diagnostic spacing |
|---|---:|---:|---:|---:|---:|
| smoke | 1e-4 | 1e-7 | 10 ms | 3 s | 20 ms |
| screen | 1e-4 | 1e-7 | 20 ms | 180 s | 25 ms |
| research | 1e-4 | 1e-7 | 10 ms | 180 s | 10 ms |
| tight | 3e-5 | 3e-8 | 5 ms | 180 s | 5 ms |

Positive-duration hybrid segments always retain their endpoints and at least a midpoint, so a short resolved slip segment is not discarded merely because it is shorter than the reporting interval. Native solver states and exact transition states are retained separately.

The runner calls CINDER's unmodified hybrid integrator in 2 s administrative checkpoints. It carries the exact state, active regime and the same CVT solver object/continuation cache onward; it never reclassifies or resets a car at a sector boundary. Each call does restart LSODA's numerical history. The interval is recorded and held common; selected final comparisons should also be checked with a larger checkpoint interval (`--checkpoint-seconds 10` or longer) and tighter settings.

Mechanical inspection is performed **after integration finishes/stops**, not between checkpoints, so report-time solves cannot perturb subsequent continuation seeds. Work diagnostics use segmentwise trapezoidal integration and do not interpolate across velocity resets. They do not constitute a new formal energy audit or a physical efficiency measurement. Both ratio definitions are explicit: `geometric_ratio_rp_over_rs` and `shaft_speed_ratio_ws_over_wp`; they need not agree during slip or helix motion.

`verify_study.py --strict-environment` also requires the exact existing Results Python/library versions. Without that flag, the installed CINDER release is still enforced and differences in the surrounding numerical environment are printed and recorded.

## Resume and experiment identity

`--resume` reuses complete case outputs only when their exact fingerprint matches. `--resume --retry-errors` reruns setup/integration/timeout/worker errors. `--rerun` regenerates the selected case directories. An interrupted car is rerun from the common initial state rather than resumed with a missing nonlinear-continuation history. Completed cars need not be rerun.

Parallel worker count and BLAS thread settings are recorded per invocation and per result for timing interpretation. Changing the road, numerical settings, fleet or code creates another campaign, preventing accidental mixing of different experiments. Redesign the road freely during discovery. Once a course and competitors are selected for the paper, keep that input set and reproduce the selected comparisons at the desired numerical resolution.

## Optional course screening and event close-ups

The course-screen script keeps the cyclic sector length fixed while changing its wavelength (the number of cycles adjusts). Each trial road is used for every selected car. With no `--execute`, it only writes profiles and prints commands:

```powershell
python studies/course-tuning-exploration/exploration/scan_courses.py --grades 35 38 40 --wavelengths 4 6 --cars R00 W90 B01 D02 D03
python studies/course-tuning-exploration/exploration/scan_courses.py --grades 35 38 40 --wavelengths 4 6 --cars R00 W90 B01 D02 D03 --jobs 4 --execute
```

For a saved run, zoom into any exact event ID or an attained course distance:

```powershell
python studies/course-tuning-exploration/analysis/inspect_event.py PATH_TO_CAMPAIGN --car R00 --event E0017 --window 0.3
python studies/course-tuning-exploration/analysis/inspect_event.py PATH_TO_CAMPAIGN --car R00 --distance 135 --window 0.8
```

Both create local force, speed, shift, support and traction plots from the saved data. They do not alter or rerun the mechanics.

## Local release-wheel test record

See `provenance/TEST_REPORT.md` for the actual local tests and the numerical-environment difference from the frozen Results environment. Local outcomes are implementation checks, not manuscript results.
