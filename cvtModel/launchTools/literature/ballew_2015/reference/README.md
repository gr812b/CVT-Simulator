# Reference data

Manual graph digitization is the only remaining source-data step for the headline comparison. Add:

- `figure_45_primary_force.csv` — Figure 45, undamped primary axial force (printed p. 62 / PDF p. 72): `time_s,primary_axial_force_n`.
- `figure_41_rpm.csv` — Figure 41, undamped pulley-speed response (printed p. 58 / PDF p. 68): `time_s,input_rpm,output_rpm`.

Digitize the full `0–5 s` traces and retain graph-axis calibration/provenance. Figure 45 must cover the complete simulation interval because the replay actuator intentionally does not extrapolate.

Use Table B1 for the exact initial speeds (`2500 rpm`, `1136 rpm`) rather than the first graph pixels. The separately listed `2.2` ratio is treated as rounded (`2500/1136 = 2.200704...`). See reconstruction A3/A6/A7.
