# Baja Track Validation

This package converts repeated Baja GPS laps and the finalized obstacle-event CSV into one ordered track coordinate, robust event/group metrics, anchor slowdown signatures, grouping QA, and simulator-validation cases.

It is designed for **relative CVT/gearing decisions and model validation**. It does not claim that GPS speed changes equal obstacle energy loss or that a historical driver trace is the optimal future lap.

## What is implemented

1. Validate the completed obstacle form and reject unresolved required `FILL` cells.
2. Clean timestamp, latitude, longitude, and speed data without applying a wide filter across obstacles.
3. Detect complete laps and reject stopped, partial, discontinuous, or poorly map-matched laps.
4. Build a reference centreline and project all laps and physical feature definitions onto one ordered coordinate, `s`.
5. Preserve every physical subfeature while combining only rows that share a completed `final_group_id` for GPS-response analysis.
6. Extract per-pass approach, immediate-entry, minimum, physical-end, traversal, specific-kinetic-energy-change, and recovery metrics.
7. Aggregate medians, IQRs, and 10th–90th percentile ranges across valid laps.
8. Audit adjacent grouping decisions using physical overlap, effective GPS resolution, and recovery between events.
9. Export reset-at-entry event cases and continuous full-lap profiles for simulator validation.
10. Compare simulator predictions against both validation modes.
11. Compare repeatable local slowdown at every physical anchor with the whole-track baseline.

## Reproduce the complete reference run

After installation, one command regenerates the entire cleaned-GPS, event-metric, grouping, signature, and simulator-export workflow:

```bash
baja-track full-run \
  --gps examples/reference_run_gps.csv \
  --definitions examples/obstacle_event_definitions_CLEANED.csv \
  --config examples/config.example.toml \
  --output results/reference_full_run
```

The top-level `FULL_RUN_REPORT.md` and `full_run_manifest.json` record the input paths, configuration, pipeline version, counts, and primary output locations. The `analysis/` folder contains the full metric run; `signatures/` contains the uniform-anchor slowdown verification.

## Installation

From this directory:

```bash
python -m pip install -e .
```

The required Python packages are declared in `pyproject.toml`.

## Required GPS input

The GPS CSV must contain:

| Column | Meaning |
|---|---|
| `timestamp` | Parseable timestamp, ordered or orderable |
| `lat` | Decimal-degree latitude |
| `lon` | Decimal-degree longitude |
| `speed_kmh` | Non-negative vehicle speed in km/h |

Extra columns are permitted. The following optional, timestamp-aligned channels are recognized automatically:

| Canonical column | Accepted aliases | Added validation context |
|---|---|---|
| `throttle_pct` | `throttle_percent`, `throttle_position_pct` | Approach/entry/event throttle, full-throttle and positive-demand fractions |
| `brake_active` | `brake`, `brake_pressed` | Approach/event braking fractions and cleaner propulsion-demand identification |
| `engine_rpm` | `rpm` | Entry/event RPM and optional power-band occupancy |
| `primary_rpm` | `cvt_primary_rpm` | Entry/event primary-pulley speed |
| `secondary_rpm` | `cvt_secondary_rpm` | Entry/event secondary-pulley speed |
| `cvt_ratio` | `ratio` | Entry/event measured ratio; keep its convention consistent with the simulator |
| `wheel_speed_kmh` | `driven_wheel_speed_kmh` | Driven-wheel versus GPS-speed slip proxy |

These channels are optional and do not change lap map matching. Their event-zone sample coverage is exported so sparse telemetry is not mistaken for a complete measurement. Higher-rate channels must currently be pre-aligned or downsampled to the GPS timestamps.

## When the completed obstacle CSV arrives

Place it anywhere and first run:

```bash
baja-track validate-definitions path/to/completed_obstacles.csv
```

Then run the analysis:

```bash
baja-track analyze \
  --gps path/to/gps.csv \
  --definitions path/to/completed_obstacles.csv \
  --config examples/config.example.toml \
  --output results/run_01
```

Strict analysis refuses unresolved required fields. The development-only flag below exists so the package can be exercised before the survey is complete:

```bash
baja-track analyze \
  --gps examples/reference_run_gps.csv \
  --definitions examples/obstacle_event_definitions_FILL.csv \
  --config examples/config.example.toml \
  --output results/provisional \
  --allow-incomplete-definitions
```

Never use a provisional run as final simulator-validation evidence; interval extents and undecided candidate groups fall back to clearly flagged assumptions.

## Metric meanings

| Metric | Definition and use |
|---|---|
| `approach_speed_kmh` | Median speed in the upstream approach zone. Describes the preceding vehicle state. |
| `entry_speed_kmh` | Speed immediately before the resolved event/group begins. Use as the event-simulation initial condition. |
| `approach_acceleration_mps2` | Signed spatial-profile acceleration proxy before entry. Reveals whether the car was already accelerating or slowing. |
| `event_min_speed_kmh` | Minimum observed speed within the physical group extent. |
| `distance_to_min_m` | Distance from group start to that minimum. Helps distinguish sharp from long responses. |
| `end_speed_kmh` | Speed at the physical end of the disturbance. Primary local validation target. |
| `post_event_speed_kmh` | Median speed in a short downstream diagnostic zone. Not a manually defined recovery exit. |
| `event_time_s` | Observed traversal time from spatial integration of `ds/v`. |
| `specific_ke_change_to_min/end_j_per_kg` | Signed `0.5(v_entry²-v_target²)`. This is observed kinetic-energy change per mass, **not obstacle energy loss**. |
| `recovery_distance_m`, `recovery_time_s` | Distance/time to recover a configurable fraction of entry speed, censored at the next event or recovery limit. |
| `effective_gps_resolution_m` | Larger of one-sample travel distance and twice median map error in the event zone. |

When available, `event_passes.csv` and `sim_event_cases.csv` also include throttle/brake demand fractions, entry and event RPM/CVT state, power-band occupancy (when bounds are configured), and a driven-wheel/GPS speed slip proxy. These help separate driver-induced slowing from terrain response; they still do not directly measure obstacle energy dissipation.

Every pass also includes raw-sample counts, map errors, quality flags, and an `aggregate_eligible` decision.

## Slowdown-signature verification

Run it independently with:

```bash
baja-track verify-signatures \
  --gps examples/reference_run_gps.csv \
  --definitions examples/obstacle_event_definitions_CLEANED.csv \
  --config examples/config.example.toml \
  --output results/signatures
```

Every physical definition is evaluated through the same ±5 m local window, regardless of its interval extent or declared group. For every eligible lap:

\[
\Delta v_{\mathrm{local}}
=
v_{\mathrm{approach}}-v_{\min,\,\pm5\mathrm{m}}.
\]

The median anchor slowdown is compared with the same statistic evaluated every 5 m around the entire observed median track profile. Defaults are:

- **Strong:** at or above the 75th track percentile and greater than 1 km/h on at least 70% of eligible laps.
- **Moderate:** at or above the 50th percentile or greater than 1 km/h on at least 50% of eligible laps.
- **Weak:** neither condition is met.
- **Insufficient laps:** fewer than six eligible laps.

All thresholds are exposed in the `[signature]` configuration block. A signature confirms repeatable speed-state structure near an anchor; it does not prove obstacle causation.

## Grouping behaviour

The completed CSV remains one row per physical subfeature.

- Same `final_group_id`: analyze the rows as one observed response.
- Different `final_group_id`: retain separate observed responses.
- `grouping_suggestions.csv`: checks the decision rather than silently overriding it.

The grouping audit considers:

- physical start/end overlap;
- separation below effective GPS resolution;
- failure to recover before the following event on most valid laps;
- the predeclared candidate cluster in the form.

Grouping affects GPS identifiability only. Logs, turns, bumps, or ruts remain separate physical rows in `resolved_feature_definitions.csv` for the simulator/resolver layer.

## Simulator-validation modes

### 1. Event-by-event validation

`sim_event_cases.csv` contains one valid pass per case. Initialize the theoretical obstacle model at the supplied measured entry speed and predict:

- minimum speed;
- physical-end speed;
- event time;
- optionally recovery distance.

Copy those predictions into `sim_event_predictions_template.csv`, then run:

```bash
baja-track compare-events \
  --observed results/run_01/sim_event_cases.csv \
  --predictions path/to/sim_event_predictions.csv \
  --output results/run_01/event_comparison
```

This mode reduces upstream confounding. It validates the local response model; it does not validate a propagated lap.

### 2. Continuous full-lap validation

Write a simulator profile with `scenario_id`, `s_m`, and `predicted_speed_kmh`, using `sim_lap_profile_predictions_template.csv` as the shape. Then run:

```bash
baja-track compare-lap \
  --observed-profile results/run_01/track_speed_profile.csv \
  --predictions path/to/sim_lap_profile.csv \
  --event-summary results/run_01/event_summary.csv \
  --output results/run_01/lap_comparison
```

This produces speed bias, MAE, RMSE, fraction inside the observed IQR, pointwise errors, and event-entry-speed errors. It tests accumulated track and powertrain behaviour.

## Important outputs

| File | Purpose |
|---|---|
| `definition_validation.csv` | Every provisional fallback or definition warning |
| `resolved_feature_definitions.csv` | All physical rows projected to `s` |
| `analysis_groups.csv` | Final GPS-response groups and physical bounds |
| `event_passes.csv` | Complete per-lap validation metrics and quality evidence |
| `event_summary.csv` | Robust aggregate targets and entry-speed distributions |
| `grouping_suggestions.csv` | Pairwise grouping audit and consistency check |
| `sim_event_cases.csv` | Event-by-event simulator inputs and observed targets |
| `track_speed_profile.csv` | Continuous median/IQR observed profile versus `s` |
| `speed_bin_summary.csv` | Median time and distance per lap in 5 km/h bins |
| `lap_summary.csv` | Retained/excluded lap evidence |
| `map_matched_gps.csv` | Cleaned GPS with lap ID, `s`, and map error |
| `track_validation_results.xlsx` | Selected tables in one workbook |
| `RUN_REPORT.md` | Run counts, interpretation rules, and limitations |

Signature outputs include:

| File | Purpose |
|---|---|
| `anchor_signature_passes.csv` | Per-lap approach/local-min evidence and quality flags |
| `anchor_slowdown_signatures.csv` | Per-anchor classification, percentile and repeatability |
| `signature_class_summary.csv` | Strong/moderate/weak counts, typical values and member lists |
| `track_slowdown_baseline.csv` | Whole-track comparison distribution |
| `anchor_slowdown_signatures.png` | Course-order visualization of the median local change |
| `SIGNATURE_REPORT.md` | Shareable results and interpretation boundary |

## Tests

The project uses the Python standard library test runner:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The suite covers strict/incomplete form intake, compound grouping, ordered metrics, specific kinetic-energy calculations, grouping suggestions, signature classification and reference reproducibility, event comparison, and lap-profile comparison.

## What GPS cannot validate alone

GPS speed alone does not identify throttle demand, braking, grade work, wheel slip, engine power-band occupancy, CVT shift delay, suspension work, tire deformation, soil deformation, or dissipated obstacle energy. Optional telemetry reduces some of those ambiguities but does not make kinetic-energy change equal terrain loss. Use these results to:

- standardize event entry conditions;
- compare design variants on paired cases;
- test ranking robustness across low/medium/high loss, concentration, and traction scenarios;
- find gearing/CVT break-even regions;
- prioritize instrumented tests.

Do not use them to claim an exact future-course lap time or a uniquely calibrated obstacle-force law.
