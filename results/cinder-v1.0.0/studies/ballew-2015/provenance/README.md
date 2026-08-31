# Provenance

Current explanatory documents are kept directly in this directory. Running
`migrate_legacy.py` additionally materializes the exact pre-port study files:

- `legacy-docs/` — original top-level Markdown documents;
- `legacy-code/` — original top-level Python implementation;
- `legacy-reference-docs/` — original reference/digitization/source READMEs;
- `migration_manifest.json` — source Git/LFS and target SHA-256 record.

This lets the cleaned results implementation evolve without erasing the exact
reasoning/code that produced the historical comparison.
