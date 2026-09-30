# CINDER localized preparation hotfix

Target: PR #505, `results-finale`, reviewed HEAD
`953d1b0423d0655002271de2af43a72c47cff87e`.

This is the follow-up to the successful Ballew hotfix. It **does not alter or
rerun Ballew**, change the installed CINDER package, retune a case, rewrite the
manuscript, standardize plot styling, or compress figures yet. It reads the
completed all-run, fixes the remaining preparation/checking paths, and tests
existing exporters in a separate output directory.

## Apply

Extract `CINDER_Localized_Prep_Hotfix` into the repository root, or use its actual
extracted path in these commands:

```sh
python CINDER_Localized_Prep_Hotfix/apply.py --repo . --check
python CINDER_Localized_Prep_Hotfix/apply.py --repo .
```

The first command writes nothing. The second applies five small existing-file
patches and adds the prep runner, helper modules, tests and instructions. All
targeted Git blobs, unique replacement anchors and Python syntax are checked
before any write. Changed local targets are refused, not overwritten. Original
files and a complete diff are retained in
`results/cinder-v1.1.2/work/localized_prep_backups/`.

The installer does not checkout, stage, commit, push, install software or download
anything. Review/commit the diff before the local run so its preparation source
has an identifiable revision. Leave the accepted older numerical executions in
place: their original source snapshots and identities remain their provenance.

## Run this localized preparation

From your repository root, using the two run directories in your uploaded reports:

```sh
python results/cinder-v1.1.2/prepare_results.py --from-run results/cinder-v1.1.2/health_runs/20260929T124106516965Z --ballew-run results/cinder-v1.1.2/health_runs/20260929T165922834300Z --fetch-lfs
```

**This launches zero CVT integrations.** It verifies and reads the completed data,
rebuilds publication inputs, repeats the relevant checks, and exercises the
existing primary, secondary and belt plot exporters. It can still take time to
hash/read the datasets and render plots. It uses the existing release-local
`.venv`, including its strict frozen-environment check.

`--fetch-lfs` permits a targeted `git lfs fetch` for the one missing primary
screening CSV if its object is not already in your local LFS cache. This requires
Git LFS to be available through Git. The object is verified by SHA256 and size,
and its data are copied into the new preparation directory. **The tracked LFS
pointer/working tree is not changed.** No simulation screen is repeated.

Do not resume the old all-run after changing its source. This command creates a
new preparation record that refers to the original numerical executions.

## Read the outcome

Output defaults to:

```
results/cinder-v1.1.2/health_runs/prep_<UTC timestamp>/
```

Open `health_report.html`. The shareable `health_summary.zip` contains reports,
logs, detailed checks, and the figure-input locations without duplicating the
large raw numerical archives. `checks/figure_rerun_inputs.json` records readiness
separately for each figure family.

A failure blocks only dependent work. Other families continue. A final nonzero
exit code means some requested work remains FAIL/MISSING/BLOCKED; it is not an
abort at the first problem. In particular, **missing solver/closure retained
archives are still MISSING**, never converted into passes or replaced by the
newly generated core sweeps.

The current manuscript figure directory is untouched. Successful smoke-test
exports go under the new run's `figures/` directory. Primary/secondary/belt output
uses their existing plotters and appearance, including their existing companion
formats. No resampling/smoothing or file-size optimization has been added.

## What was actually wrong

### Primary: missing Git LFS payload

The all-run recorded `primary_screen.csv` with SHA256
`a28304b418f949993bc64df4be2d46a04abb4c250f8dd91189dbf07bfcf1fede`.
That is exactly the pointer text in the repository—not the 72-row table.
The required LFS object is 10,366 bytes with SHA256
`4499dfb01068c0f21bf528d0d4ef1861c3c6a3b043d165b787395ca8de4b9dbb`.

The table is used by the existing torque-ramp figure and is not removed. The
preparer now checks it up front, accepts an explicit `--screen-csv`, and records
its identity. `diagnosis.json` includes the original-report/pointer comparison.
The earlier hypothesis that the historical screen was merely a redundant gate
was too broad; the actual fix is to restore the intended data.

### Belt: Windows manifest separators

The main preparation already wrote the new audit before moving-state extraction.
However, it stored `str(relative_path)` keys, which contain backslashes on
Windows. The moving-state reader looked up forward-slash keys, causing the
observed `KeyError: 'unloading_nominal_full/terms.csv.gz'`.

New manifests use portable `/` paths. Historical keys are normalized when read;
conflicting hashes or unsafe paths still fail. The moving-state step now receives
its main audit path explicitly, and its source hashes must match that same
preparation. This is not a physics change or permission to combine executions.

### Course: omitted deadzone margin cells

The exporter saved flyweight force components in both engaged and deadzone
states, but wrote the mechanism-margin field only when engaged contact existed.
The union-column CSV therefore has blank flyweight-margin cells in deadzone
rows. A blanket finiteness check treated these omitted cells as failed physics.

The hotfix reconstructs only this known blank deadzone field from the three
already-retained signed full-flyweight force contributions. In frozen CINDER,
that sum is the `FixedPivotFlyweightForce` compressive-contact margin. The
reconstructed force is still tested against the existing unilateral tolerance.
Negative force still fails. Literal NaN/Inf, missing force components, unknown
mechanisms and engaged missing margins are not excused. Raw rows are not edited,
and both sides of contact/support transitions remain checked.

The resulting audit reports the reconstruction count and minimum, then the
course bundle retains all 15 cases' rows, modes and event sides without filtering
out launch, stops or rollback. This prepares the numerical input layer; it does
not invent the missing manuscript compositor.

## Secondary and accepted Ballew evidence

Secondary story preparation uses the existing full-primary baselines directly;
its dependency no longer runs through the screening-table preparation. Existing
secondary/backshift calculations are reprocessed and checked, not reintegrated.

The accepted Ballew run is verified against its original report/output hashes
and executed-source snapshots. Adding unrelated prep code must not relabel it or
force its ODE runs again. The current generic `simulation_fingerprint` remains
conservative, so use this accepted-run registration rather than attempting to
pass the old run off as a newly executed current-generator cache.

## Retained solver and closure evidence

The old all-run did not include the retained publication archives required by
those exact plots. A new core sweep is a different piece of evidence. Supply the
actual retained folders through `--paths`, for example:

```json
{
  "solver_artifacts": "D:/CINDER-evidence/solver/evidence/artifacts",
  "closure_artifacts": "D:/CINDER-evidence/closure/evidence/reviewed"
}
```

```sh
python results/cinder-v1.1.2/prepare_results.py --from-run results/cinder-v1.1.2/health_runs/20260929T124106516965Z --ballew-run results/cinder-v1.1.2/health_runs/20260929T165922834300Z --fetch-lfs --paths retained_paths.json
```

The closure folder must include `contour_audit/`. The code verifies the retained
execution records before export. Archive names and restoration instructions
are listed in the delivery package’s `RETAINED_EVIDENCE.md` and the per-study MISSING detail reports.
These external archives were not present in the preparation workspace and are
not included in this delivery.

A third optional `--paths` key, `primary_screen`, can identify an already-restored
CSV with the exact required SHA256. No Git LFS access is then necessary for it.
Relative paths are relative to the JSON file.

## Useful variants

```sh
# Show the non-integrating execution graph only:
python results/cinder-v1.1.2/prepare_results.py --from-run PATH_TO_ALL_RUN --ballew-run PATH_TO_BALLEW_RUN --dry-run

# Recheck selected families only; reports remain explicitly partial:
python results/cinder-v1.1.2/prepare_results.py --from-run PATH_TO_ALL_RUN --only primary secondary belt course --fetch-lfs

# Skip the staged exporter smoke tests:
python results/cinder-v1.1.2/prepare_results.py --from-run PATH_TO_ALL_RUN --ballew-run PATH_TO_BALLEW_RUN --skip-export-smoke

# Resume THIS new prep record, not the old numerical all-run:
python results/cinder-v1.1.2/prepare_results.py --from-run PATH_TO_ALL_RUN --ballew-run PATH_TO_BALLEW_RUN --fetch-lfs --output PATH_TO_PREP_RUN --resume
```

Use the original mode/paths/scope when resuming. Changed source or original input
report identities require a new output. Previously attempted generated products
are preserved in `previous_attempts/` rather than discarded. There is no default
wall timeout; `--step-timeout-hours` applies an explicit limit to each subprocess.

## What is ready afterward, and what remains

If primary/secondary/belt/course checks pass, their corrected publication inputs
and staged exports can be used in the full figure-reproduction pass. The new
`course_plot_inputs.npz`/`course_bundle.json` preserve the numeric course evidence
for that exporter work. The exact nine course manuscript composites still need
their original compositor recovered or a reviewed equivalent registered. This
package does **not** substitute the generic, narrower shift-shape plots.

`figure_input_locations.json` is an evidence handoff, not automatically a valid
`run_results.py --paths` file: the later figure-only workflow must retain the
original identities of reused Ballew and other numerical runs.

Compression and format changes remain the next pass, limited to where they help.
There is no blanket figure restyling here. Manuscript numerical updates and the
final reviewed Results commit remain explicit freeze tasks.

## Testing

See the delivery package’s `TESTING.md`. The new helper, guard, archive-identity, LFS, numeric-bundle,
installer and execution-graph tests were run. One installed-CINDER identity test
must run in your pinned environment. The complete repository/raw archive suite
was not available for end-to-end execution here; no full-prep PASS is claimed in
advance. The local command is what supplies that remaining evidence.
