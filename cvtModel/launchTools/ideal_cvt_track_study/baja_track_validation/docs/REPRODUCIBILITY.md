# Reproducibility guide

## Inputs

The complete workflow requires:

1. a GPS CSV with `timestamp`, `lat`, `lon`, and `speed_kmh`;
2. a strict obstacle-definition CSV with no unresolved `FILL` cells;
3. a TOML configuration file.

Optional timestamp-aligned throttle, brake, engine/CVT speed, explicit CVT ratio, and driven-wheel-speed channels are retained when present.

## Install and run

```bash
python -m pip install -e .

baja-track validate-definitions examples/obstacle_event_definitions_CLEANED.csv

baja-track full-run \
  --gps examples/reference_run_gps.csv \
  --definitions examples/obstacle_event_definitions_CLEANED.csv \
  --config examples/config.example.toml \
  --output results/reference_full_run
```

## Output structure

```text
reference_full_run/
├── FULL_RUN_REPORT.md
├── full_run_manifest.json
├── analysis/
│   ├── cleaning_summary.csv
│   ├── lap_summary.csv
│   ├── reference_centreline.csv
│   ├── resolved_feature_definitions.csv
│   ├── analysis_groups.csv
│   ├── event_passes.csv
│   ├── event_summary.csv
│   ├── grouping_suggestions.csv
│   ├── sim_event_cases.csv
│   ├── track_speed_profile.csv
│   └── simulation prediction templates
└── signatures/
    ├── anchor_signature_passes.csv
    ├── anchor_slowdown_signatures.csv
    ├── signature_class_summary.csv
    ├── track_slowdown_baseline.csv
    ├── anchor_slowdown_signatures.png
    └── SIGNATURE_REPORT.md
```

## Deterministic contracts

- Course order comes from the definition `sequence` column.
- Physical grouping comes from repeated `final_group_id` values.
- Every GPS sample is projected onto one ordered centreline coordinate, `s`.
- Event aggregates use only passes with `aggregate_eligible=true`.
- Signature classification uses the explicit `[signature]` thresholds in the configuration.
- The manifest records the complete effective configuration and package version.

Floating-point differences between supported NumPy/pandas versions may change only the final insignificant digits. A material count or classification change should be treated as a regression and investigated.

## Interpretation boundary

The full run is reproducible, but the physical world remains uncertain. GPS-only speed response cannot uniquely separate braking, grade, turning, tire slip, terrain deformation, and obstacle dissipation. The outputs are intended for paired design comparisons, validation envelopes, break-even analysis, and uncertainty sweeps—not exact terrain-force reconstruction.
