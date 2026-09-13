# Ballew study provenance

This directory documents the assumptions and implementation history required to
audit the Ballew comparison without relying on generated result files.

- `RECONSTRUCTION.md` — normative source-to-CINDER reconstruction assumptions.
- `CINDER_FIXES.md` — general CINDER implementation defects exposed while
  constructing the benchmark and why the v1.0.0 corrections are physically
  appropriate.
- `NUMERICAL_STABILITY.md` — numerical-refinement and broad stability-sweep
  methodology. Results are generated fresh into `../artifacts/`.

Source files and digitization provenance live under `../reference/` rather than
here because they are executable benchmark inputs, not narrative documentation.
