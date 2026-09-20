# Consolidated-layout test report

Date: 2026-09-20.

This report concerns the directory reorganization, not a new physical study.
Historical test reports in this tree describe their original package versions.

## Inputs and mechanics

- All five final course/fleet/presentation/criteria JSON inputs are byte-identical
  to the separate-final package. The selected manifest metadata was renamed and
  its lock refreshed; numerical and physical choices were not changed.
- The final course evaluator, model adapter, tune transformations, diagnostics,
  fleet executor, and metrics match the inherited implementation hashes.
- The shared baseline and Results helpers passed the existing locked hashes.
- The final verifier successfully built all ten CINDER model assemblies and
  checked common boundary/mechanism identities.
- The default final preparation produced exactly 12 selected jobs: ten unified
  course histories and R00/U55 on the independent 800 m flat.

## Automated checks

- 72 final unit/input/isolation tests passed.
- 68 relocated exploration unit/input/path tests passed.
- 14 migration tests passed: dry run, both old folders, absent folders,
  destination conflicts, source modifications, empty directories, repeat runs,
  symlink refusal, live-lock refusal, injected-error rollback and navigation.
- All 52 supplied Python files parsed successfully.
- A final-only source snapshot (with exploration absent) passed its 72 tests,
  with the single optional exploration-presence check skipped.

## Migration of the supplied artifacts

The real migration test staged the uploaded artifact tree from
`artifacts(20260920-183308).zip` under the former exploratory folder, along with
legacy source files and a representative completed final smoke result. It also
added a locally edited source comment and a user-notes file to test preservation.

- All 7,130 regular uploaded artifact files were included.
- 7,409 files in total were moved and verified against their pre-move SHA-256.
- Both old top-level study folders were removed by the moves.
- The migrated source changes and original numerical/provenance files survived.
- Across 33 HTML pages, all 1,980 checked relative local links resolved.
- A repeated migration found nothing to move and preserved the results.

## Execution and resume

- The consolidated final runner executed the separate three-second R00/D02
  smoke suite with two spawned processes, generated its reports, and packed it.
  Both outcomes were the expected `time_limit` for that short run.
- Resume retained both cases, scheduled zero integrations, and left both
  diagnostic CSV SHA-256 hashes unchanged.
- The final smoke return ZIP passed CRC checking and contained no exploration
  or archived-history paths.
- The relocated exploratory runner executed a three-second R00 smoke test.
- Initial course-scan preparation, feature-scan preparation and the previous
  unified-candidate preparation ran from their new `exploration/scans/` paths.
- A no-legacy-folder dry run created no files.

## Scope

Execution checks used the actual CINDER 1.1.2 wheel from the supplied release
artifact. The surrounding test interpreter/dependencies differ from the frozen
Results environment; diagnostic runs used the explicit mismatch flag and retain
that warning. They are packaging/compatibility checks, not replacement final
Results data.

The complete 12-trajectory campaign was not rerun for this organization-only
change. Run it in the existing frozen Results environment for the manuscript
output. No stopping criteria, model equations or settling thresholds were
relaxed.
