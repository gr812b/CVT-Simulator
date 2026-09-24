# RC28 replacement search

This is a deliberately narrow follow-up to the final-v2 RC28 construction-audit rejection. It does **not** modify the selected final fleet or `course-tuning/run.py`.

The search preserves the original dynamic fixed-pivot flyweight mechanism, mass geometry, pivot, arm, roller, first 10--14 mm of the physical ramp, all CVT/vehicle boundaries, and the locked 732 m course. Only the smooth ramp tail is varied. The original final-v2 RC28 definition is retained as `RC28X`, an expected-rejection control.

The runner is audit-first. Every definition is decoded through the same shared `defaults.reference_model.decode_reference_case` path used by the final study. A definition rejected by CINDER's released fixed-pivot construction audit is recorded in `definition_screen.csv` and is never integrated. `RC28X` is never integrated even if a different environment unexpectedly accepts it.

From `results/cinder-v1.1.2`:

```bash
# Optional fast check: geometry audit only
python studies/course-tuning/exploration/scans/scan_rc28_replacements.py --preflight-only --pack

# Main search: audit all definitions, then run only accepted replacements + R00
python studies/course-tuning/exploration/scans/scan_rc28_replacements.py --jobs 4 --resume --pack
```

Open `replacement_screen.html` in the generated `exploration/artifacts/rc28_replacement_v1__.../` folder. The page links the exact rejection reasons, full-course gallery, free-upshift curve comparison, and `falling_curve_candidates.csv`, which sorts accepted/running cases by the measured opening-flat free-upshift slope. No candidate is automatically promoted to the final fleet.
