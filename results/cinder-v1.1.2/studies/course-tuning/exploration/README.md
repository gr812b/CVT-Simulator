# Course-tuning exploration

These tools preserve the previous course/fleet investigations within the same
`course-tuning` study. They are separate from the selected root `run.py` and
write only under this directory's `artifacts/`.

## The normal final run

From `results/cinder-v1.1.2`, the final command is:

```bash
python studies/course-tuning/run.py --jobs 4 --resume --pack
```

Nothing below is required for that command. The working final road and fleet
remain locked at the study root.

## Browse earlier results

After migrating the old folders, open `../migration_report.html` relative to
this directory, or open a campaign's own `artifacts/<campaign>/index.html`.
Original HTML relative links and numerical files are preserved. To refresh the
navigation index after creating more campaigns:

```bash
python studies/course-tuning/tools/migrate_layout.py --index-only
```

## Run an exploration explicitly

All examples below start in `results/cinder-v1.1.2`, with its environment active.

```bash
# Inspect the original competitor intentions without running CINDER
python studies/course-tuning/exploration/run.py --list

# Original exploratory fleet; writes exploration/artifacts only
python studies/course-tuning/exploration/run.py --preset research --jobs 4 --resume

# Prepare the old feature-screen plan; add --execute to actually run it
python studies/course-tuning/exploration/scans/scan_features.py
python studies/course-tuning/exploration/scans/scan_features.py --groups cyclic --execute --jobs 4 --resume

# Earlier unified-candidate check, retained as exploration
python studies/course-tuning/exploration/scans/finalize_course.py --execute --jobs 4 --resume

# Check the relocated exploration's unit/input tests
python studies/course-tuning/exploration/verify_study.py
```

The exploratory runner retains its configurable courses, presets, fleets and
selected-car options. Its configuration is now `exploration.json`, not a second
maintained-study manifest. The original 32-car fleet, extended 38-car fleet and
10-car candidate fleet remain under `inputs/`.

## Rebuild figures from saved exploratory data

Pass the current relocated campaign path:

```bash
python studies/course-tuning/exploration/analysis/shift_curves.py "studies/course-tuning/exploration/artifacts/<campaign>"
python studies/course-tuning/exploration/analysis/final_course_checks.py "studies/course-tuning/exploration/artifacts/<unified-candidate-campaign>"
python studies/course-tuning/exploration/analysis/compare_features.py "studies/course-tuning/exploration/artifacts/feature_explorations/<id>/plan.json"
```

The feature comparison resolves archived absolute campaign paths against the
new artifact root without rewriting the original plan. Use the actual path
reported by migration if an `imported_.../` conflict container was required.

## History and cache identities

`history/<stamp>/course-tuning-exploration/` contains the original installed files,
including any local modifications. They are retained as an exact source archive;
the adapted runnable copy is here at the exploration root. Historical test
reports under `provenance/` retain their original dates and environment details.

Old outputs are not relabelled as new runs. Relocation changes the exploratory
source fingerprint, so a new invocation creates its own campaign; within that
campaign `--resume` behaves as before. Editing exploratory code or adding old
artifacts does not change the selected final study's fingerprint.

Detailed original protocols remain in `V2_REFERENCE.md`, `V2_QUICKSTART.md`, and
`V3_FINAL_CHECK_README.md`. Their current command paths have been relocated;
reported historical measurements have not been changed.


## RC28 replacement search

A focused audit-first replacement search for the rejected final-v2 `RC28` ramp is available at `scans/scan_rc28_replacements.py`. See `rc28_replacement/README.md`. It is exploratory only and does not change the root final runner.
