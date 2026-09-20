# Single-study layout revision

The selected final physics and experiments are unchanged. `study.json` now names
`course-tuning` and declares the locally contained, independently run
`exploration/` subtree. The selected-input lock was updated only for this
manifest metadata; the course, competitors, supporting flat, presentation
selection and settling-criteria JSON files remain byte-identical to the previous
final package.

## Final execution

`run.py` still executes ten uninterrupted unified-course histories and the two
supporting 800 m flat histories. The course evaluator, tune transformations,
CINDER model adapter, trajectory executor, diagnostics, comparison metrics and
figure/report code have not changed.

`infrastructure/common.py` fingerprints only final execution modules/tests.
`infrastructure/selection.py` snapshots that same final tree plus its inputs,
documentation and shared defaults. Both exclude exploratory code/artifacts,
archived installations and migration logs. Changes in those excluded areas do
not invalidate a final run or enter its portable return archive.

## Exploration

The supplied explorer is the original package with its v2 and v3 updates applied.
Its release-root paths account for the extra directory level. Its former inner
`exploration/` directory is named `scans/`, and its configuration is
`exploration.json` rather than a second current study manifest. The original
fleet, feature-screen and candidate-course inputs remain available.

A relocated feature-plan reader resolves previously recorded absolute paths
without modifying historical manifests. The explorer fingerprints its own
executable tree, excluding artifacts and archived source history.

## Migration

`tools/migrate_layout.py` previews moves by default. `--apply` preserves exact
copies of the installed legacy source trees under history/provenance, relocates
whole artifact trees to the corresponding final or exploratory destination,
and verifies every file against its original SHA-256. Existing targets are
never overwritten; whole incoming artifact trees receive distinct import
containers when necessary. The journal records all moves and original hashes.

This does not rewrite historical identities or adopt old runs into a new cache.
New executions use the consolidated source fingerprint. Subsequent `--resume`
operations reuse only complete, hash-verified cases of that new identity.

The root tests cover final isolation. The exploration tests cover relocated
paths. The migration tests are independent standard-library filesystem tests
under `tools/tests/`.
