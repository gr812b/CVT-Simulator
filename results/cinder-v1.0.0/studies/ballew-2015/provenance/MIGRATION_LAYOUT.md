# Legacy-to-results migration layout

The old benchmark is not discarded. It is split into **canonical current code**
and an **exact historical archive** so future results can be rerun without
losing the reasoning and evidence that produced the benchmark.

| Legacy location | New location | Role |
|---|---|---|
| `reference/**` | `reference/**` | exact thesis, WPD projects, raw exports and prepared references |
| `results/**` | `artifacts/historical-v1.0.0/**` | exact historical outputs, convergence and stability evidence |
| root `*.md` | `provenance/legacy-docs/**` | exact reconstruction, final interpretation, diagnostics and package notes |
| root `*.py` | `provenance/legacy-code/**` | exact legacy benchmark implementation |
| cleaned port | study root + `benchmark/**` | canonical rerunnable v1.0.0 study |
| new run outputs | `artifacts/rerun-v1.0.0/**` | regenerated results from the published wheel |

`__pycache__` and `.pyc` files are the only legacy files intentionally excluded.

The migration reads the frozen `cinder-v1.0.0` Git tag rather than relying on
the old working-tree directory. Consequently the legacy `launchTools` location
may be deleted after migration and verification without breaking this study.

Git-LFS objects are smudged and integrity-checked against the SHA-256 OID stored
in their pointer. Every migrated file is recorded in
`provenance/migration_manifest.json` with its source path, Git blob, target path,
byte count and SHA-256.
