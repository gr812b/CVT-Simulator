# Baja track validation run

## Run summary

- Clean GPS rows: 4462 of 4474
- Complete laps detected: 13
- Laps retained: 11
- Reference track length: 1773.6 m
- Physical definition rows: 40
- Final analysis groups: 37
- Aggregate-eligible event passes: 403 of 481
- Definition warnings: 0
- Grouping decisions requiring review: 8
- Optional telemetry channels: none

## Primary validation artifacts

- `sim_event_cases.csv`: reset-at-entry cases for obstacle-model validation.
- `event_summary.csv`: median, IQR, and 10th–90th percentile observed targets.
- `track_speed_profile.csv`: full-lap observed median and variability envelope.
- `grouping_suggestions.csv`: whether adjacent responses are distinguishable in this GPS data.
- `sim_event_predictions_template.csv`: fill with event-simulation predictions, then run `compare-events`.
- `sim_lap_profile_predictions_template.csv`: fill with a simulated speed profile, then run `compare-lap`.

## Interpretation rules

- Entry speed is the immediate pre-group initial condition. Approach speed and approach acceleration remain separate diagnostics.
- End speed is measured at the physical disturbance end. Post-event and recovery quantities are diagnostics, not manually defined exits.
- Specific kinetic-energy change is observed vehicle-state change in J/kg. It is not obstacle energy loss.
- Grouping combines only the GPS-observed response; individual physical subfeatures remain in `resolved_feature_definitions.csv`.
- Event-by-event cases reset to measured entry conditions to isolate the obstacle model. Full-lap comparison propagates continuously and tests accumulated model/CVT behaviour.

## Fundamental limitations

Without optional telemetry, GPS alone cannot identify throttle demand, braking, grade work, wheel slip, CVT ratio, engine RPM, suspension work, soil deformation, or dissipated obstacle energy. Even with telemetry, grade, tire slip calibration, and terrain losses remain confounded. Use paired design comparisons and uncertainty sweeps; do not interpret these outputs as an absolute reconstruction of track forces or driver behaviour.
