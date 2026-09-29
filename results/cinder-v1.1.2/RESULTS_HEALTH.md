# Results corrections and local health runner

This workflow keeps the installed **CINDER 1.1.2** mechanics unchanged. It repairs
Results-side construction/reporting/checking and writes into a **new output tree**.
It does not promote figures into the manuscript, retune cases, or alter the
quasi-static comparisons.

## Start here

From the repository root, after applying and preferably committing the code patch:

```bash
python results/cinder-v1.1.2/run_results.py --mode correct
```

The launcher uses `results/cinder-v1.1.2/.venv/Scripts/python.exe` on Windows or
`.venv/bin/python` on macOS/Linux. The existing `verify_environment.py` still
requires the release-local Python 3.12 environment and pinned dependencies.
The launcher itself uses only the standard library. It does not install,
upgrade, or modify the environment.

**This may take a long time.** `correct` runs the five existing Ballew benchmark
calculations with the corrected mass and rechecks retained evidence elsewhere.
`all` also regenerates selected publication calculations and the core numerical
sweeps; that can take hours or longer. No duration estimate has been measured
for this combined runner.

```bash
# Show the plan, without writing files or running calculations.
python results/cinder-v1.1.2/run_results.py --mode correct --dry-run

# Check identified existing evidence; no CVT integrations.
python results/cinder-v1.1.2/run_results.py --mode check

# Regenerate selected publication cases/core sweeps and run the health checks.
python results/cinder-v1.1.2/run_results.py --mode all
```

`all` does **not** mean every old exploratory script in the repository. In
particular, the archived dense solver-population search, targeted folded-branch
archives, and the retained primary 72-case screening table remain identified
historical evidence. Their maintained publication routes are checked separately;
new core sweeps are not silently substituted for those archives.

## Where to look

The output directory is printed at startup and normally has the form
`results/cinder-v1.1.2/health_runs/<UTC timestamp>/`.

- `health_report.html`, `.md`, `.json`: final status and links to logs.
- `health_summary.zip`: reports/logs/check details for sharing, not the full raw archive.
- `checks/`: individual checks, corrected belt mass and old/new slip accounting.
- `data/`: new raw executions. `prepared/`: derived or verified compact evidence.
- `figures/`: staged exports, **not** replacements for `docs/.../figures/`.
- `source_manifest.json`, `source_snapshot/`, `run_context.json`: source/input identity.
- `previous_attempts/`: preserved partial/replaced outputs when resuming.

Independent work continues after a failed step. A dependent step is **BLOCKED**
rather than run on stale inputs. Missing retained evidence is **MISSING**, not a
pass. The report is updated between steps and on ordinary errors/interruptions.
A final exit code of **2** means some work failed, was blocked, or was missing;
it does not mean the runner stopped at the first error. Exit **0** means all
requested steps passed. An explicit `--only` selection is recorded as partial
scope. Neither outcome automatically approves the paper's conclusions.

There is deliberately no unconditional `ready_to_freeze=true` shortcut. Register
the exact course manuscript compositor (F03), make any external retained data
available (F05), and review the corrected benchmark values before freezing.

## Retained data outside the default folders

Copy `results_paths.example.json`, enter only paths that differ from the defaults,
and pass it with `--paths`. Relative paths resolve relative to that JSON file.
Do not enter filenames for ZIP files where a directory is required; use the
existing study import commands to recover the registered evidence first.

```bash
python results/cinder-v1.1.2/run_results.py --mode correct --paths my_results_paths.json
```

The default course check uses its `artifacts/latest_final.txt` pointer. A missing
or stale pointer is reported. `course_suite` can identify the suite containing
`suite.json` explicitly. The solver completion check needs original cache pairs
`config.json` + `metadata.json`; compact plot inputs alone do not prove the
termination status of all original executions.

## Resume and isolation

```bash
python results/cinder-v1.1.2/run_results.py --mode correct --output results/cinder-v1.1.2/health_runs/my-check
python results/cinder-v1.1.2/run_results.py --mode correct --output results/cinder-v1.1.2/health_runs/my-check --resume
```

Resume requires the same source/input identity, mode, selected scope, interpreter,
and external-path configuration. Successful generation is reused only when its
recorded output hashes match. Checks and postprocessing run again. Failed/partial
outputs are moved aside before retrying. Never change the source during a run;
a detected change prevents treating the result as one consistent execution.

Execution is serial at the outer level. The course runner is also invoked with
one worker. This favors low memory use and isolated LSODA work over maximum
throughput. `--step-timeout-hours N` is an optional per-step timeout; the default
imposes no new wall-time limit. Ctrl+C stops the active process tree and leaves
the current status/outputs available for a later resume. After a machine crash,
remove a stale `RUNNING.lock` only after confirming no process is still active.

## What changes scientifically

| ID | Implemented change | Consequence |
|---|---|---|
| C01 | Normalize Ballew density by the centroid-path length and check the **resolved assembly** mass. | All five existing Ballew executions must be regenerated together. The old mass is about 0.9731 kg, not the claimed 1 kg. |
| C02 | Add sliding-only, sign-checked loss channels; retain signed sticking-drift work separately. | Loss numbers/plot may change. The motion equations are not altered by this reporting change. Old observer channels are retained, not renamed. |
| C03 | Read executed secondary inertia in generic force/mass diagnostics; preserve original physical inertia as diagnostic metadata on the Results-only quasi-static law. | Generic larger-secondary diagnostics change. The final publication extraction already corrected these quantities. No added energy audit of the quasi-static comparison. |
| C04 | Check applicable finite loads and contact/support margins at starts and ends, not just interior rows; verify retained event sides and case seals. | Existing course curves are not automatically changed. A newly exposed failure must be reviewed. |
| C05 | A failed reduced-belt local-loading check produces a nonzero exit; missing/NaN values cannot pass. | Recheck the retained 42-run set; do not assume that a successful process alone proves admissibility. |
| C06 | Require true completion and coverage of the requested interval on solver cache writes/reads/comparisons. | Reclassify/recover any incomplete execution; no blanket rerun of a valid sweep. |
| F01 | Stronger source/input cache identity; fresh Ballew output tree by default. | Old 0.973 kg nominal output cannot enter a new 1 kg refinement comparison. |
| F02 | Bind main belt, moving-state and event evidence; prepare them from one selected raw directory. | Separate prepared bundles; no hidden default raw-data source. |
| F04 | `prepare_secondary_story.py --primary-dir` accepts verified fresh full-primary baselines; the original hash-checked ZIP option remains. | A new selected publication run need not depend on an obsolete delivery ZIP. |

C02 uses `P_pair = lambda * N * v_rel`. In a sliding regime, valid friction has
`P_pair <= 0` and the loss is `-P_pair`. In a sticking regime the ideal relative
speed is zero; a small nonzero numerical residual is recorded as **signed drift
work**, not physical sliding loss. The existing energy-study tolerance of
`1e-5 W` is used for tiny energy-adding sliding roundoff; any clipped amount is
reported. Larger wrong-sign sliding power fails. The `slip_accounting.json`
file quantifies the old/new difference on the actual regenerated trajectory.

For F02, a legacy compact bundle is only re-bound after its existing main/moving
hashes and individual event hashes have been reconciled. A fresh bundle is
prepared directly from the raw runs. The checker states whether raw files were
available; compact-only verification is not reported as a fresh integration.

## Still not solved by this package

**F03:** the exact nine course manuscript composites have not been recreated here.
The maintained course diagnostics and general reports are not interchangeable
with the manuscript's complete opening/rollback/matched-speed selections. The
later figure pass must recover/register the exact extraction before promotion.

**F05:** missing historical archives are not invented or downloaded automatically.
Their absence remains visible. A local path in a health report is not an externally
available reproducibility package.

The figure-format/vector/raster/compression pass is deferred. A hash inventory
of existing manuscript assets is recorded, but their bytes are not modified.

## Code tests

```bash
results/cinder-v1.1.2/.venv/bin/python -m unittest discover -s results/cinder-v1.1.2/results_health/tests -v
```

On Windows use the same interpreter under `.venv/Scripts/python.exe`.
These fast tests cover loss signs/masks, event boundaries, completion, cache
identity and failure-tolerant orchestration. The repository-backed tests resolve the
actual Ballew mass and check the reduced helix’s diagnostic inertia when CINDER
and the checkout are present. None of these tests
replaces the numerical campaign and its health checks.
