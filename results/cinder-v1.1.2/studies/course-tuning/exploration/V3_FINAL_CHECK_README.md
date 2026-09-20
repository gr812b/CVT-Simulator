# Unified-course final check

This update adds one combined course and one focused ten-car confirmation. It
retains the existing simulation and plotting machinery. The added hill is long
enough to investigate an interior travelling operating point, rather than only
the initial backshift. The cyclic section has more repeated loads.

## Install and run

Extract this update **inside `results/cinder-v1.1.2`**, alongside the installed
v2 course-tuning study. It adds files under `studies/course-tuning/exploration/`;
it does not replace the old course, fleet, reports, or shared defaults.
Activate the existing CINDER 1.1.2 Results environment.

From `results/cinder-v1.1.2`:

```sh
# Optional: run the study tests, including the new final-check tests.
python -m unittest discover -s studies/course-tuning/exploration/tests -p "test*.py"

# Resolve the new inputs without simulating.
python studies/course-tuning/exploration/scans/finalize_course.py

# Run all ten cars on the same unified course and build both reports.
python studies/course-tuning/exploration/scans/finalize_course.py --execute --jobs 4 --resume
```

The default is the existing **tight** preset: relative tolerance `3e-5`, absolute
tolerance `3e-8`, maximum step `0.005 s`, saved diagnostics every `0.005 s`.
No physical switching/admissibility tolerance is changed. Separate worker
processes retain the existing LSODA isolation.

For a first small check:

```sh
python studies/course-tuning/exploration/scans/finalize_course.py --execute --cars R00 W85 H28 B01 --jobs 4 --resume
```

Then run the all-car command above. The unchanged campaign fingerprint allows
those completed cars to be reused. `--preset research` is available for a faster
preview, but the final settling report deliberately checks solved derivatives,
which can be noisier than state curves at coarser settings. Do not relax the
settling criterion just to label a preview run steady.

`--preset smoke` ends after three simulated seconds. `time_limit` is expected
in that plumbing check. `--no-plots` retains all numerical output and skips
figure generation. Use `--resume --retry-errors` to retry interrupted/error
cases. Physical course non-completion is not automatically rerun.

## The common course

All distances are signed travelled distance along the road, as in the existing
study. Full throttle is unchanged throughout.

| Interval (m) | Feature |
|---|---|
| 0–120 | Flat launch and upshift |
| 120–132 | Smooth entry into main hill |
| 132–212 | 38° constant climb |
| 212–224 | Smooth exit from main hill |
| 224–264 | Level recovery |
| 264–336 | Six 12 m periods, ±32° grade, zero mean |
| 336–348 | Level separation |
| 348–356 | Smooth entry into moderate hill |
| 356–596 | 240 m constant 18° climb |
| 596–604 | Moderate-hill exit |
| 604–624 | Level recovery |
| 624–636 | Descent entry |
| 636–696 | −22° descent |
| 696–708 | Descent exit |
| 708–732 | Final level segment |

The profile through the original main hill and its recovery (0–264 m) is
identical to the preceding study. The same ±32° / 12 m cyclic waveform is now
repeated six times. Its existing 6 m physical amplitude taper is retained at
each end; four whole periods are completely outside those tapers.

The 18° angle is retained. Only its constant-grade hold is extended from 45 m
to 240 m, providing a sustained approach to the interior operating state as well
as the initial backshift. No condition tells the integrator to stop shifting,
hold a ratio, or reset a car at the hill. No part of the road changes in response
to a particular car. All cars traverse it from the original common initial
state; a car that fails the main climb does not resume downstream.

`inputs/course_unified_candidate.json` is intentionally a new file. Course
selection remains explicit: edit a copy to run an alternative. Any edit creates
a separate campaign through the normal runner fingerprint.

## The ten entrants

`inputs/competitors_final_check.json` contains the eight previously nominated
cases unchanged: **R00, W85, W115, H28, B01, U55, D01, D02**.

Two additional cases isolate the two primary tuning changes in D02:

| ID | Tip-mass scale | Primary-preload scale | Comparison |
|---|---:|---:|---|
| D02 | 0.65 | 1.15 | Original adverse case |
| D02_M | 1.00 | 1.15 | Restore only the tip mass and its associated moments |
| D02_P | 0.65 | 1.00 | Restore only the primary spring compression |
| R00 | 1.00 | 1.00 | Common reference |

These are repair hypotheses, not forced improvements. The two intervention
cases let the data distinguish increased centrifugal action from reduced spring
opposition. The same dynamic fixed-pivot flyweight law, full dynamic bilateral
helix, shaft boundaries, vehicle properties, friction, geometry, and driver rule
are retained for every entrant. Mass-moment updates use the existing resolver.

## Reports

The wrapper prints the campaign path, the familiar `index.html`, and a new
`final_checks/index.html`. The existing report gains one link to the final
checks; its content is not replaced.

The existing whole-course plots, detailed mechanical/event views, and individual
phase-coloured **primary RPM versus secondary RPM** curves remain. All ten cars
are selected for detailed plots by the final-check wrapper.

The extra report includes:

* a moderate-hill comparison in time measured from **each car's own** hill entry;
* shift, shift rate, vehicle speed, acceleration, and primary RPM through entry,
  constant grade, and exit, with markers at hold entry and exit;
* individual-car hill views;
* chronological engine-speed, vehicle-speed, and power plots for main-hill
  slow-progress/rollback cases, with the saved exact event IDs marked;
* observed-settling classifications and the final-window state values;
* every evaluated settling window in CSV;
* the existing cycle-by-cycle response metrics, with tapered cycles identified;
* opening-flat upper-stop reachability and whole-course outcome summaries.

Relative hill-entry time is only a plotting origin. It does not impose equal
entry states, phase-align a reset, or splice trajectories. The whole-course
plot still uses the common physical road coordinate.

Saved records:

```
<campaign>/final_checks/
    index.html
    course_outcomes.csv
    settling_summary.csv
    settling_windows.csv
    definitions.json
    moderate_hill_*.png
    <car>/shift_mm.png
    <car>/speed_m_s.png
```

`settling_summary.csv` contains the last-window means even for a failing case,
so such rows must not be reported as equilibria without checking
`settling_status`. `case_requires_review`, `hill_not_reached`, `hill_incomplete`,
and `hold_too_short_to_test` remain distinct.

Rebuild these checks from an existing saved campaign without simulation:

```sh
python studies/course-tuning/exploration/analysis/final_course_checks.py "PATH/TO/CAMPAIGN"
```

The same command also works on the earlier 18° campaign and correctly identifies
that its 45 m hold is too short to establish the declared steady window.

## What counts as observed interior settling?

The report tests five-second trailing windows every 0.25 seconds and at the
last constant-grade sample. A passing window requires **all** of the following:

| Quantity | Limit |
|---|---:|
| Forward vehicle speed | >0.10 m/s |
| Distance in shift from both travel stops | >0.25 mm |
| Absolute shift rate | ≤0.05 mm/s |
| Absolute vehicle acceleration | ≤0.01 m/s² |
| Absolute primary and secondary speed rates, each | ≤2 rpm/s |
| Absolute belt acceleration | ≤0.01 m/s² |
| Absolute shift acceleration | ≤0.0005 m/s² |
| Shift range over the window | ≤0.10 mm |
| Vehicle-speed range | ≤0.05 m/s |
| Primary/secondary RPM range, each | ≤10 rpm |
| Belt-speed range | ≤0.05 m/s |
| Largest gap in saved samples | ≤0.10 s |

It also requires engaged **free** shift, the prescribed constant grade,
unchanged contact mode, no physical CVT transition in the window, and no
inspection error. Maximum derivative magnitudes are used, not percentiles that
could hide isolated excursions. Case-wide review flags remain visible and
prevent an unqualified headline steady classification.

The derivatives come from the solved RHS, not differencing of plotted curves.
The ordinary growing distance/shaft-angle host is excluded from stationarity:
this is a travelling operating state. No damping ratio, periodic attractor,
exact equilibrium, or asymptotic stability is established by this finite-window
criterion.

If a car is still evolving at hill exit, the report says so. A flat line at a
travel stop cannot pass as an interior operating point. A near-constant shift
position while the vehicle is still accelerating also cannot pass.

The `sustained_tail_verified_duration_s` records the span covered by consecutive
passing sampled windows through exit; `first_passing_window_end_m` records the
first completed qualifying window and is a sampled diagnostic, not an exact
hybrid event.

## Scope and decisions after the run

This is a single-road confirmation, not another broad sweep. The decisions are:
Does the longer cyclic sequence make the regime/event differences readable?
Does the moderate hill establish sustained interior operation for useful tunes?
Do D01, D02 and U55 retain their distinct diagnostic roles, and what do the
one-change D02 interventions reveal?

Slow-progress/rollback stops are finite-run observations. Errors or loss of the
retained belt/contact topology are not labelled inability of a real vehicle to
climb. The road model still assumes pure rolling and permanent tyre contact,
with no suspension or airborne whoops. The original full-throttle engine map
and its extrapolated overspeed tails are untouched.

The long-flat 800 m experiment remains separate supporting evidence for
persistent under-shifting. It is not inserted into the main road and is not
rerun by this command.
