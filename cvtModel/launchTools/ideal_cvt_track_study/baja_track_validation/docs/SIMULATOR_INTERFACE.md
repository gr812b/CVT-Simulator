# Simulator interface

## Event cases

Use `sim_event_cases.csv`. The stable join key is `case_id`.

Required predictions:

| Column | Units |
|---|---|
| `case_id` | identifier copied unchanged |
| `predicted_min_speed_kmh` | km/h |
| `predicted_end_speed_kmh` | km/h |
| `predicted_event_time_s` | s |
| `predicted_recovery_distance_m` | m; may be blank when the simulator does not model recovery |

The comparison output includes signed error, absolute error, percentage error where meaningful, bias, MAE, RMSE, median absolute error, observed IQR, and MAE divided by observed IQR.

When present in the GPS log, the same event cases retain observed throttle/brake demand fractions, RPM, CVT ratio, wheel-slip proxy, and per-channel coverage. A simulator may use these as filtering or diagnostic context, but the required prediction contract above remains unchanged.

## Full-lap profile

Required prediction columns:

| Column | Meaning |
|---|---|
| `scenario_id` | design/scenario label; optional, defaults to `baseline` |
| `s_m` | ordered track distance |
| `predicted_speed_kmh` | simulator speed |

The profile need not use the identical `s` grid; observed statistics are interpolated to the prediction points.

## Recommended simulator diagnostics retained separately

When available, keep these alongside the required predictions rather than forcing them into GPS-derived targets:

- engine RPM and power deficit;
- CVT ratio and time at ratio bounds;
- primary/secondary slip state;
- clutch-loss energy;
- wheel-torque reserve;
- traction-limited time;
- obstacle, tire-slip, and other loss channels.

Those explain prediction error and design tradeoffs even though GPS alone cannot validate them directly.
