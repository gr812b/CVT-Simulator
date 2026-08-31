# Ballew 2015 baseline comparison

This is the untouched CINDER baseline using the documented A1-A9 reconstruction choices. No parameter was fitted to Figure 41.

- completed: `True`
- termination: `final_time_reached`
- segments/transitions: `252` / `251`

## Pointwise comparison at digitized reference times

| Quantity | N | MAE | RMSE | Max abs. error | RMSE / mean reference |
|---|---:|---:|---:|---:|---:|
| Primary RPM | 113 | 1744.204 rpm | 1796.106 rpm | 2047.881 rpm | 71.880% |
| Secondary RPM | 64 | 36.160 rpm | 38.255 rpm | 52.225 rpm | 3.187% |
| Speed ratio | 158 | 1.409000 | 1.451341 | 1.733736 | 69.606% |

## Interpretation guardrails

- Figure 41 is digitized model output, not experimental data.
- A1/A9 vehicle-side reconstruction is intentionally not tuned to improve these errors.
- Figure 45 is prescribed to CINDER; it is an input, not a validation output.
- CINDER and Ballew represent internal belt deformation differently; see A8.
