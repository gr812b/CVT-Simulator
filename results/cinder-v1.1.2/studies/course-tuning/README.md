# CINDER 1.1.2 — common-course tuning study

This is the selected Section 4.5 case set. It runs the complete simulations and
builds one offline report. No parameter sweep or automatic case selection is run by the root entry point.

## Install

Extract this ZIP **inside `results/cinder-v1.1.2`**. The only new directory is:

```text
results/cinder-v1.1.2/studies/course-tuning/
```

This single study contains the selected final workflow at its root and the
previous exploratory workflow under `exploration/`. The root `run.py` never
runs an exploration, reads exploratory artifacts, or includes the exploration
tree in its cache identity or final return ZIP.

The release's existing `defaults/baja/` and `defaults/reference_model/` are
prerequisites, as is the installed CINDER wheel. This package does not replace
shared files. On a fresh installation no previous course package is required.

### Move your existing study folders once

Stop any course simulations that are still running. From
**`results/cinder-v1.1.2`**, run:

```bash
python studies/course-tuning/tools/migrate_layout.py --apply
```

Omit `--apply` for a preview. The migration uses only the standard library and
recognizes both former sibling folders when present:

| Existing material | New location |
|---|---|
| `course-tuning-exploration/artifacts/` | `course-tuning/exploration/artifacts/` |
| Other files in `course-tuning-exploration/` | `course-tuning/exploration/history/<stamp>/course-tuning-exploration/` |
| `course-tuning-final/artifacts/` | `course-tuning/artifacts/` |
| Other files in `course-tuning-final/` | `course-tuning/provenance/layout_history/<stamp>/course-tuning-final/` |

The old top-level folders are moved, not left as additional maintained studies.
The ZIP already supplies the working exploration code in its new location,
including the initial course scans, feature scans, and unified-course candidate
check. Its former inner `exploration/` scripts now live under `exploration/scans/`.
The exploratory configuration is `exploration/exploration.json`; the sole current
study manifest is the root `study.json`.

Every original file is retained and SHA-256-checked after the move, including
any local code edits. Local edits are archived exactly as found, not silently
merged into the supplied working code. The per-file migration record identifies
where each original file went. Keep those archives until you have reviewed any
local changes you need to bring across.

If a destination artifact folder already exists, the incoming **whole artifact
tree** is placed in an `imported_<old-name>_<stamp>/` child; existing results are
never overwritten or merged ambiguously. This preserves relative HTML links.
The generated `course-tuning/migration_report.html` links the actual relocated
reports. Original manifests, CSV/JSON/NPZ files and historical paths inside them
are not rewritten to pretend the results were generated in the new layout.

The migration refuses source symlinks and unresolved live-lock files. Ordinary
caught errors reverse the completed moves; a forcibly killed migration leaves
its journal and `MIGRATING.lock` for inspection. Do not run it concurrently with
a study. Repeating the command after a successful migration is harmless.

**Previously generated outputs remain available, but are not automatically
reused by the renamed final runner.** The source/manifest layout change produces
a new fingerprint. The first final run in this layout regenerates the selected
cases; `--resume` then reuses completed cases within this layout as usual.

### Directory layout

```text
studies/course-tuning/
├── study.json
├── run.py                        # Selected final 15 trajectories only
├── verify_study.py
├── inputs/                       # Locked final road, fleet, and criteria
├── infrastructure/
├── experiments/
├── analysis/                     # Final plots, tables, offline report
├── tests/                        # Final tests, including isolation checks
├── artifacts/                    # Final runs + final return ZIPs
├── exploration/
│   ├── README.md
│   ├── exploration.json
│   ├── run.py                    # Earlier exploratory fleet runner
│   ├── inputs/                   # Original, feature, and candidate inputs
│   ├── scans/                    # Course/feature scans + candidate check
│   ├── infrastructure/
│   ├── experiments/
│   ├── analysis/
│   ├── tests/
│   ├── artifacts/                # All exploratory campaigns/reports
│   └── history/                  # Original installed files, if migrated
├── tools/migrate_layout.py
└── provenance/
    ├── migrations/               # Per-file move/verification records
    └── layout_history/           # Original separate-final installation
```

The course, numerical settings, stopping rules and shared model remain unchanged. The selected fleet is revision 3: P300, RC10 and RC40L are retained from the shift-shape exploration, R26B7 replaces the RC28 geometry rejected by the frozen CINDER 1.1.2 construction audit, and D02_M150 provides the selected high-primary-force comparison on the D02 repair axis. W115 and B01 remain exploratory/supporting cases. The final report includes focused spring/ramp shift-shape, severe-hill, repair/over-correction, and mechanism figures.

Activate the existing Results environment. The expected environment is Python
3.12, `cinder-cvt==1.1.2`, NumPy 2.5.2, SciPy 1.18.1 and Matplotlib 3.11.1. Do not
use an editable CINDER install or add `cvtModel/src` to `PYTHONPATH`.

## Run everything

From **`results/cinder-v1.1.2`**, with its environment activated:

```bash
python studies/course-tuning/verify_study.py
python studies/course-tuning/run.py --jobs 4 --resume --pack
```

These commands are the same in macOS/Linux terminals and PowerShell. `--jobs 4`
uses four independent processes, not four threads. Use a smaller value to reduce
CPU/memory use. BLAS thread counts default to one per process.

The verifier checks the selected inputs, shared reference, unit tests, and all thirteen
model assemblies. It does not integrate trajectories. The second command runs:

| Experiment | Cars | Road |
|---|---|---|
| `unified_course` | R00, W85, P300, RC10, R26B7, RC40L, H28, U55, D01, D02, D02_M, D02_M150, D02_P | The selected 732 m course |
| `flat_800m` | R00, U55 | A separate 800 m flat |

**Fifteen trajectories in total.** Both experiments use the final tight
settings: LSODA, relative tolerance `3e-5`, absolute tolerance `3e-8`, maximum step
`0.005 s`, diagnostic interval `0.005 s`, and observation limit `180 s`.
The earlier exploratory flat used the research preset; this final package
regenerates the two supporting flat cases at the common tight settings.

All cases begin from the common baseline initial conditions. There are no
sector restarts, hidden controls, required failure outcomes, forced equilibria,
or inserted quasi-static actuator comparisons.

## One output location

The runner prints a directory such as:

```text
studies/course-tuning/artifacts/final_v3__<fingerprint>/
├── index.html                     # Start here
├── suite.json                     # Exact suite identity, settings and environment
├── completion.json                # Completeness and review flags
├── tables/                        # Combined outcomes, events, settings, metrics
├── unified_course/
│   ├── index.html                 # Familiar course/family/mechanical report
│   ├── shift_curves.html          # All and phase-coloured individual shift curves
│   ├── final_checks/index.html    # Interior settling, cycles and failure chronology
│   ├── shift_shape.html           # Selected shift-curve shape + mechanism comparisons
│   ├── figures/
│   └── cases/<ID>/                # Full CSV/JSON/NPZ records for every case
├── flat_800m/
│   ├── index.html
│   ├── shift_curves.html
│   ├── figures/
│   └── cases/<ID>/
└── provenance/
    ├── study/                     # Snapshot of study source and selected inputs
    └── shared_results/            # Snapshot of the shared reference used
```

Open the top-level `index.html` directly in a browser. No web server or network
connection is required. The latest directory is also written to
`studies/course-tuning/artifacts/latest_final.txt`.

With `--pack`, the complete current dataset is archived beside that folder as:

```text
final_v3__<fingerprint>_return.zip
```

**Return that ZIP.** It includes the reports, every generated figure, all case
records, checkpoint/sample NPZs, exact inputs and source snapshots. It excludes
only superseded attempts, Python caches and the live runner lock. It does not
include unrelated exploratory campaigns. There is no need to ZIP the entire
release's artifacts tree.

## Fixed course

Distance is signed travelled distance along the road, not horizontal distance.
Full throttle is unchanged throughout.

| Distance (m) | Feature |
|---|---|
| 0–120 | Flat launch and upshift |
| 120–132 | Smooth entry into the main hill |
| 132–212 | Constant 38-degree climb |
| 212–224 | Hill exit |
| 224–264 | Level recovery |
| 264–336 | Six 12 m cycles at ±32 degrees, zero mean; 6 m end tapers |
| 336–348 | Level separation |
| 348–356 | Entry into the moderate hill |
| 356–596 | Constant 18-degree hold |
| 596–604 | Moderate-hill exit |
| 604–624 | Level recovery |
| 624–636 | Entry into the descent |
| 636–696 | Constant −22-degree descent |
| 696–708 | Descent exit |
| 708–732 | Final level segment |

Four cyclic periods are entirely outside the tapers. The 800 m flat is a
separate supporting experiment, not an extension spliced into this road.

## Fixed competitors

Each modification is applied to the same baseline. Mass percentages refer to **replaceable tip mass**, not total flyweight mass. The P300 rate case changes spring stiffness and explicitly adjusts installed compression so the spring force matches the reference at the low-ratio engagement geometry. Ramp cases preserve the fixed-pivot hardware and mass properties while changing only the physical ramp profile; the dynamic mechanism map is rebuilt from that geometry.

| ID | Changes relative to R00 |
|---|---|
| R00 | None |
| W85 | 85% tip mass |
| P300 | 3× primary spring stiffness, with matched low-ratio spring force |
| RC10 | First 10 mm of ramp retained, 5 mm C3 blend, arc tail ending at 10° |
| R26B7 | First 10 mm retained, 7 mm C3 blend, arc tail ending at 26°; accepted by the frozen release construction audit |
| RC40L | First 18 mm retained, 5 mm C3 blend, late arc tail ending at 40° |
| H28 | 28° helix instead of 20° |
| U55 | 55% tip mass |
| D01 | 130% tip mass, 80% primary/secondary axial preload, 28° helix, 240° torsional twist |
| D02 | 65% tip mass and 115% primary axial preload |
| D02_M | Reference tip mass; retain D02's 115% primary preload |
| D02_M150 | 150% tip mass; retain D02's 115% primary preload |
| D02_P | Retain D02's 65% tip mass; restore reference primary preload |

W115 and B01 remain under `exploration/` and are not part of this selected final fleet. Every selected case retains the same full dynamic fixed-pivot flyweight mechanism, dynamic bilateral/slotted secondary helix, engine/vehicle boundaries, belt/contact model and initial state.

The report writes `unified_course/shift_shape.html` using only the opening-flat, free-shifting, stick-stick interval for shape descriptors. These descriptors do not fit stop-held, slipping, backshift or downhill portions into one shift-curve slope.

## Resume, incomplete runs and errors

`--resume` reuses cases only when their exact fingerprint, required files and
file hashes match. It starts unfinished cases again from their original initial
conditions; it does **not** stitch a new solve onto a previously saved partial
trajectory. Completed cases remain untouched.

A case with an observed rollback or slow-progress stop is a valid recorded
outcome. It is not given an invented finishing time, discarded, or repeatedly
rerun in search of a finish. A numerical error or model-domain stop is reported
separately. The thirteen common-course physical outcomes are never hardcoded as expected results.

To retry completed numerical/setup/timeout errors:

```bash
python studies/course-tuning/run.py --jobs 4 --resume --retry-errors --pack
```

Old/incomplete attempts are moved under `previous_attempts/` rather than silently
deleted. They are excluded from the return ZIP, whose case folders contain the
current attempts.

To rerun an interrupted subset first:

```bash
python studies/course-tuning/run.py --only unified_course/D02 flat_800m/U55 --resume --jobs 2
```

This does not reduce the final inventory. Missing cases remain visible; run the
normal command afterward to finish the complete set. Exit code `2` indicates
incomplete or flagged results; exit code `0` means the requested dataset was
assembled without such flags. That is an execution result, not physical
validation or a guarantee that every car finished.

If a process is forcibly killed, it may leave `RUNNING.lock`. Confirm no process
is writing that output folder before removing this one lock file and resuming.
Two runners must not use the same suite directory simultaneously.

## Optional plumbing and reporting commands

A three-second R00/D02 smoke test goes into a **different** `smoke__...` directory:

```bash
python studies/course-tuning/run.py --smoke --jobs 2 --resume
```

`time_limit` is expected in that short check. It never counts as the final run.

Verify and write the resolved inputs without integrating:

```bash
python studies/course-tuning/run.py --prepare-only
```

Rebuild all figures/reports or repack an existing final folder without integrating:

```bash
python studies/course-tuning/analysis/report_final.py "/path/to/final_v3__fingerprint" --pack
```

Generate a close-up from an exact event ID in a saved main-course case:

```bash
python studies/course-tuning/analysis/inspect_event.py "/path/to/final_v3__fingerprint/unified_course" --car D02 --event E0017 --window 0.5
```

Use an event ID that exists in that case's `events.csv`. This reads saved data
only. Repack afterward to include any additional views.

`--allow-environment-mismatch` is reserved for explicitly labelled diagnostic
checks outside the frozen dependency environment. It never permits a different
CINDER release or an editable source install. Such outputs are prominently
marked as non-frozen and are not substitutes for the manuscript run.

## Figures and metric interpretation

The familiar plots are retained for **every** selected car, not just an automatic
winning subset: motion, RPM, shift, forces, traction, powers, local normal load,
support reactions, and regime histories. The report also contains named
comparisons for launch, severe hill, cyclic loading, interior hill operation,
the D02 repairs/over-correction, and descent. Competitor colours are stable across comparison
plots; individual primary-versus-secondary RPM curves use road-sector colours.
Chronology and segment/reset boundaries are retained.

The report is data-driven. Interior settling is assessed with the previously
agreed five-second window, state ranges, solved derivatives, free-shift/interior
conditions, sampling coverage and no physical event inside the window. The
criteria and all assessed windows are saved. Failed checks are not relaxed.
Cyclic tables distinguish tapered from full-amplitude periods, net motion from
backshift excursions, and free shifting from stop occupancy.

The course model contains longitudinal road load, not suspension, wheel lift or
tire slip. The engine map retains its supplied extrapolated overspeed-resisting
tail; any absorption there is not a measured closed-throttle CH440 law. Saved
slip-work integrals are sampled diagnostics, not a replacement for the separate
formal energy audit. Runtime records distinguish setup, integration and
post-processing; machine and dependency versions accompany them.
