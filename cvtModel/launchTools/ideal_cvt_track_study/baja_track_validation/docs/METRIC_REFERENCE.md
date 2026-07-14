# Metric reference

## Ordered event state

| Metric | Definition | Primary use |
|---|---|---|
| `approach_speed_kmh` | Median speed 30–10 m before physical event start by default | Upstream state and likely pre-event slowing |
| `entry_speed_kmh` | Median speed in the final 5 m before physical start | Reset-at-entry simulator initial condition |
| `approach_acceleration_mps2` | Half the spatial slope of speed squared | Signed acceleration/deceleration proxy |
| `event_min_speed_kmh` | Minimum interpolated speed inside the physical extent | Local response target |
| `distance_to_min_m` | Distance from physical start to minimum | Sharp versus distributed response |
| `end_speed_kmh` | Median speed around the physical endpoint | Primary local validation target |
| `post_event_speed_kmh` | Median speed in a downstream diagnostic zone | Recovery context |
| `event_time_s` | Spatial integral of `ds/v` through the event | Traversal-time target |
| `recovery_distance_m` | Distance to recover a configured fraction of entry speed | Recovery demand |
| `recovery_time_s` | Integrated time to that recovery point | Time consequence |

## Kinetic-state proxies

\[
\Delta e_k=\frac{1}{2}\left(v_{\mathrm{entry}}^2-v_{\mathrm{target}}^2\right).
\]

`specific_ke_change_to_min_j_per_kg` and `specific_ke_change_to_end_j_per_kg` are vehicle-state changes per unit mass. They are not identified obstacle-energy losses because propulsion, braking, grade, rolling resistance, turning, and terrain remain mixed.

## Signature evidence

`median_approach_to_local_min_kmh` uses a uniform ±5 m anchor window, independent of the physical event extent. `track_slowdown_percentile` ranks that median against the identical statistic sampled around the whole track. `fraction_laps_slowdown_gt_threshold` measures repeatability across eligible laps.

## Quality evidence

Every pass retains raw sample counts, median/maximum map error, nominal travel per GPS sample, effective GPS resolution, eligibility, and semicolon-separated quality flags. Aggregate medians and percentiles exclude ineligible passes but the raw rows remain available for audit.

## Simulator-validation outputs

- `sim_event_cases.csv`: measured reset-at-entry cases for isolating local model response.
- `track_speed_profile.csv`: continuous full-lap observed envelope for accumulated model/CVT validation.
- comparison commands: signed error, absolute error, percentage error where meaningful, bias, MAE, RMSE, observed-IQR normalization, and event-entry error.
