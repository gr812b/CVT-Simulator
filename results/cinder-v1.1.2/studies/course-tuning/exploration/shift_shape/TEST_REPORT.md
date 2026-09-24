# Shift-curve shape exploration — implementation and test record

## Tested scope

The addition contains 12 new rate/profile definitions and three unchanged reference/mass controls. The final course-tuning study and its original source files are unchanged. The numerical experiment uses the selected 732 m spatial course, common initial conditions, unchanged full throttle, full dynamic fixed-pivot flyweights and the dynamic bilateral/slotted secondary helix.

The spring cases deliberately change both stiffness and installed preload to match ONE declared initial component force or torque. The ramp cases change physical geometry after a preserved nose; they do not impose a shift/RPM law or rescale a force. All new rate/ramp cases retain the original flyweight mass moments and fixed hardware inertias.

## Local environment

- Python: 3.13.5 (main, Jul 15 2026, 20:25:40) [GCC 14.2.0]
- Platform: Linux-6.18.44-x86_64-with-glibc2.41
- CINDER: 1.1.2, installed released wheel.
- NumPy: 2.3.5; SciPy: 1.17.0; Matplotlib: 3.10.8.
- Wheel SHA256: `f9c454963006d701b33197bdef3be60abebc591199aef7f4b52f37a7159310c3`.

The surrounding dependencies differ from the frozen Results environment. These are local implementation/execution checks, not a replacement for the user's frozen-environment rerun, physical validation, or a new convergence study. The full-course test used the exact shared Results reference helpers whose hashes match the selected final study's lock, and the baseline's canonical JSON hash also matches that lock.

## Automated and installation checks

- 32 new unit/input tests passed: unchanged controls and common physics; non-mutating configuration resolution; exact spring matching; rate-dependent force gradient; mass-moment preservation; physical ramp-prefix and endpoint construction; bad knob/rate/preload rejection; shape metrics; physical-branch/reset separation; incomplete support; file-integrity reuse; concurrent-output locking; final fingerprint isolation.
- The 72 existing final-study tests passed.
- The 68 existing exploratory-study tests passed.
- Both-endpoint slope selection now explicitly uses one connected upshift path, including a regression test for an earlier partial excursion followed by a later complete upshift.
- Original consolidated files were compared byte-for-byte with the delivered consolidated ZIP; none changed.
- A fresh overlay installation passed `--list` and `--prepare-only` from an unrelated working directory. The overlay introduces new files only.
- Final-source three-second R00/P200/RC28 smoke execution passed, with expected `time_limit` outcomes. `--resume` reused all three cases and left their diagnostic CSV SHA256 values unchanged. Return ZIP creation succeeded.
- Local relative HTML links were audited; the generated smoke gallery had no missing targets.

The full-course integrations used the final tune definitions, geometry constructors, and physical runner. While these were executing, several reporting/metadata guards were tightened (including disconnected-path slope selection and report-only locking). Those guards were tested separately; the table below was recomputed from saved full-course data with the delivered analysis code. No physical run data were modified or substituted.

## Complete 732 m course check

| ID | Status | Finish time [s] | Shift slope [primary rpm / 1000 secondary rpm] | Offset-removed shape RMS [rpm] | Inspection errors | Sampled review flags |
|---|---|---:|---:|---:|---:|---:|
| R00 | finished | 75.957 | 23.717 | 0.000 | 0 | 0 |
| W85 | finished | 76.169 | 32.854 | 8.139 | 0 | 0 |
| W115 | finished | 75.689 | 15.297 | 6.699 | 0 | 0 |
| P050 | finished | 75.902 | 5.497 | 7.895 | 0 | 0 |
| P200 | finished | 76.043 | 58.101 | 15.365 | 0 | 0 |
| P300 | finished | 76.097 | 89.569 | 30.025 | 0 | 0 |
| S050 | finished | 75.947 | 19.477 | 1.937 | 0 | 0 |
| S200 | finished | 75.976 | 32.092 | 3.846 | 0 | 0 |
| T067 | finished | 75.932 | 13.031 | 4.858 | 0 | 0 |
| T150 | finished | 75.990 | 39.339 | 7.183 | 0 | 0 |
| RC10 | finished | 79.102 | 250.808 | 125.702 | 0 | 0 |
| RC28 | finished | 75.889 | -220.841 | 110.295 | 0 | 0 |
| RL30 | finished | 76.031 | -186.950 | 119.005 | 0 | 0 |
| RC35L | finished | 75.941 | -5.839 | 37.843 | 0 | 0 |
| RC40L | finished | 76.002 | -5.757 | 44.986 | 0 | 0 |

These slopes are the secant between 20% and 80% active shift along one eligible opening-flat path. All fitting excludes clutch slip, support-held ratios, backshift and the later terrain. A positive value means primary RPM rises as secondary RPM rises; it does not mean a better-performing vehicle. The RMS removes one constant RPM offset over each candidate's recorded common secondary-RPM interval with R00. Pair-specific supports differ, so this is not a universal ranking metric.

This is a check of the supplied dynamics at the existing tight settings: relative tolerance 3e-5, absolute tolerance 3e-8, maximum step 5 ms, diagnostic step 5 ms, 180 s maximum observation. The solver can take smaller internal steps. No numerical tolerance, clamping law, boundary or course is changed for any entrant.

A preliminary 14-second launch pass also exercised all 15 definitions. Its `time_limit` outcomes were expected. Early probe/launch tests used a semantically equivalent local reference-loader copy; the full-course confirmation above and final-source smoke checks used the exact selected shared helpers.

## Ramp construction checks

Every supplied profile passed CINDER's released full-travel fixed-pivot construction audit. Samples of the physical ramp, actual roller contact coordinate, complete mechanism map and spring maps are saved per case. The preserved nose/prefix retains the original first profile segments; the new joins use the released C3 constructor and are not manually clipped or relaxed.

Aggressive developer drafts were rejected before fleet selection:

| Draft | Released construction finding | Action |
|---|---|---|
| Early circular 40-degree tail | No mathematical roller contact near 18.7523 mm local sheave travel | Excluded; no reduced travel or relaxed check |
| Early circular 32-degree tail | Second simultaneous physical contact near 10.0087 mm local sheave travel | Excluded |
| Early straight 40-degree tail | C3 audit rejection and lost contact branch | Excluded |

The delivered later-onset 35/40-degree arcs, early 10/28-degree arcs and straight 30-degree tail passed the stock checks. This is model-geometry admissibility, not strength, packaging, fatigue, wear or manufacturing certification. Spring matching likewise does not certify an available physical spring.

## Selection guidance

The data now contain strong rising, falling and localized-shoulder shift curves. The primary spring-rate cases provide a gentler gradient comparison. Secondary compression and torsional rate cases test whether those alternative force gradients supply useful curve changes at this baseline. Only after inspecting the complete course should any candidate be promoted into the final fleet. The final runner and its selected inputs were not changed.

## Final report-generation audit

The full 15-car gallery was regenerated from saved full-course data with the delivered analysis code: 254 PNG figures and 654 checked relative HTML links, with no missing targets. The final-source smoke/resume gallery also had no missing targets. All 100 pre-existing consolidated files remained byte-identical.
