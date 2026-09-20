# Final course study — local test report

## Scope

This is the test record for the separate `studies/course-tuning-final` package.
The selected physical inputs, ten tune dictionaries and underlying integration,
assembly, diagnostic and metric kernels were retained from the accepted uploads.
The supporting R00/U55 800 m flat is regenerated at the final tight controls.

The local tests used the official released `cinder-cvt==1.1.2` wheel. Its SHA-256
was `f9c454963006d701b33197bdef3be60abebc591199aef7f4b52f37a7159310c3`.
**Local dependencies differ from the manuscript environment:** Python 3.13.5,
NumPy 2.3.5, SciPy 1.17.0 and Matplotlib 3.10.8 on Linux x86_64.
The required manuscript environment remains Python 3.12, NumPy 2.5.2,
SciPy 1.18.1 and Matplotlib 3.11.1. All local integration checks explicitly used
`--allow-environment-mismatch`, and their reports are marked non-frozen.
These are execution/regression checks, not a substitute for the user's frozen
run, a new convergence study, or physical validation.

## Checks actually completed

- **66 unit/input tests passed.** These cover the selected course, consistent
  tip-mass moment edits, unchanged boundary definitions, interpolation and
  first-passage behavior, reset-aware integration/plots, cyclic detrending,
  finite-window settling, fixed selection, cache integrity, archive contents,
  and output-lock handling.
- **All ten full model assemblies were built and checked.** Their dynamic
  flyweight law, bilateral dynamic helix law, shaft-boundary classes and
  boundary inertias match the common model contract.
- **Twelve full selected-case executions completed.** Eight main-course cars
  finished, the two observed main-course non-finishers were retained, and both
  supporting flat cases finished. No numerical/setup/worker errors or recorded
  inspection errors were found in this local execution. Non-finishing physics
  is not forced or treated as a passing numerical exception.
- **A fresh installation was tested without an exploratory study directory.**
  Only the new final study and the shared release defaults were present. The
  fixed-input prepare operation and parallel three-second R00/D02 smoke test
  completed, including reports and a return ZIP. Both short cases correctly
  report `time_limit`; the report says smoke-only, not final evidence.
- **Resume/reporting was exercised on the completed twelve-case suite.** It
  retained every completed case, scheduled zero integrations, and rebuilt the
  combined tables, plots, reports and archive. SHA-256 hashes and modification
  timestamps of all twelve diagnostic CSVs were unchanged.
- **Offline report references were checked:** 6 HTML pages and
  585 local links; no broken references. The complete
  report contains 246 PNG figures, including every selected car,
  shift curves, settling/cyclic views, failure chronology and named comparisons.
- **The generated return archive passed ZIP CRC validation**, with
  1666 members. It contains current results and source
  snapshots and excludes superseded attempts, Python caches and live locks.

## Recorded local case outcomes

| Experiment | Case | Outcome | Finish time (s) |
|---|---|---|---:|
| unified_course | R00 | finished | 75.957246 |
| unified_course | W85 | finished | 76.168944 |
| unified_course | W115 | finished | 75.688855 |
| unified_course | H28 | finished | 75.883153 |
| unified_course | B01 | finished | 76.275846 |
| unified_course | U55 | rollback | — |
| unified_course | D01 | finished | 80.502140 |
| unified_course | D02 | progress_limited | — |
| unified_course | D02_M | finished | 76.095625 |
| unified_course | D02_P | finished | 88.704045 |
| flat_800m | R00 | finished | 49.239879 |
| flat_800m | U55 | finished | 65.051333 |

A dash means there is no finishing time; no extrapolated finishing time is
substituted for a failed climb. All emitted metrics, including any finite-window
settling failures, are retained without changing thresholds. The complete local
settling diagnostics and exact test environment are in `LOCAL_TEST_RECORD.json`.

### Local settling flag retained

W115 passes earlier observation windows but fails the local final-window
shift-acceleration check. The prior user-supplied frozen-environment run passed
its settling checks. This new local diagnostic uses different dependencies;
no criterion was relaxed and no result was overwritten to make them agree.
Re-run in the frozen environment before making a manuscript settling claim.
The two non-finishers did not reach the moderate hill and are explicitly marked
as unobserved there, not assigned settled values.

## What the installation ZIP contains

Only `studies/course-tuning-final/`: source, fixed inputs, README, linkage and
provenance notes, and tests. It does not contain any generated local trajectories,
old exploratory studies, shared-default replacements, CINDER wheel or environment.
The locally generated return archive above was used to test packing; it is not
silently supplied as the manuscript dataset. Run the final entry point in the
frozen Results environment and return its own `_return.zip`.
