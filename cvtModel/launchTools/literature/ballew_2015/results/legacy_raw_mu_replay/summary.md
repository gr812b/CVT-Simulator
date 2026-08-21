# Ballew 2015 baseline comparison

This is the untouched CINDER baseline using the documented A1-A9 reconstruction choices. No parameter was fitted to Figure 41.

- completed: `True`
- termination: `final_time_reached`
- segments/transitions: `88` / `87`

## Pointwise comparison at digitized reference times

| Quantity | N | MAE | RMSE | Max abs. error | RMSE / mean reference |
|---|---:|---:|---:|---:|---:|
| Primary RPM | 113 | 1889.186 rpm | 1913.893 rpm | 2037.602 rpm | 76.594% |
| Secondary RPM | 64 | 16.869 rpm | 19.237 rpm | 35.096 rpm | 1.603% |
| Speed ratio | 158 | 1.587854 | 1.604886 | 1.793340 | 76.970% |

## Interpretation guardrails

- Figure 41 is digitized model output, not experimental data.
- A1/A9 vehicle-side reconstruction is intentionally not tuned to improve these errors.
- Figure 45 is prescribed to CINDER; it is an input, not a validation output.
- CINDER and Ballew represent internal belt deformation differently; see A8.
