# Provenance

The promoted actuator study depends on four result-generation scripts and their
three shared Baja setup/support files from the frozen `cinder-v1.1.2` tag.

They are not copied from the mutable working tree at run time. `verify_study.py`
resolves the annotated tag to commit

`7637a38b4fb9ec21dfb953c1c80a27ec5f389654`

and `study_support.py` obtains each source blob using local `git show`, checking
the exact Git blob SHA recorded in `../upstream_manifest.json`.

The scripts are then executed with the active
`results/cinder-v1.1.2/.venv` Python interpreter, whose environment verifier
requires the published `cinder-cvt==1.1.2` package.

This split is deliberate:
- published CINDER wheel = frozen mechanics implementation;
- tagged launch/result utilities = frozen study construction and comparator
  definitions;
- this results study = release-scoped orchestration, status boundaries, and
  artifact organization.
