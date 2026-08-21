> **Final-study interpretation:** Wall-clock/Pareto timing is not used as a headline Ballew comparison. The canonical paper-facing interpretation is [`NUMERICAL_STABILITY_RESULTS.md`](NUMERICAL_STABILITY_RESULTS.md), which emphasizes convergence, actual adaptive step scale, accepted integration-step count, and substantive hybrid-event stability. Timing fields remain available only as exploratory/provenance data.

# CINDER numerical stability / performance stress test

Place `run_numerical_stability_stress_test.py` in:

`cvtModel/launchTools/literature/ballew_2015/`

Run from `cvtModel/`.

```powershell
# First verify that the harness works on your checkout.
python launchTools/literature/ballew_2015/run_numerical_stability_stress_test.py --preset smoke

# Useful broad sweep for inspection / plotting.
python launchTools/literature/ballew_2015/run_numerical_stability_stress_test.py --preset quick --timing-repeats 3

# Paper-oriented sweep across a wider solver-control range.
python launchTools/literature/ballew_2015/run_numerical_stability_stress_test.py --preset full --timing-repeats 3 --compare-methods

# If interrupted, continue the completed grid points.
python launchTools/literature/ballew_2015/run_numerical_stability_stress_test.py --preset full --timing-repeats 3 --compare-methods --resume
```

The default output directory is:

`launchTools/literature/ballew_2015/results/numerical_stability_stress_test/`

## Why this is better than the four-point plot

The old convergence plot asked only whether four already-small solver settings changed the Ballew comparison metrics. Since all four points were deep inside the converged region, the plot was necessarily almost empty.

This stress test asks a broader question: **over what numerical operating region does CINDER continue to produce the same physical trajectory, how much numerical work is required there, and where does degradation begin?**

The sweep spans several orders of magnitude in both maximum allowed adaptive step and error tolerance. Failed or degraded cases are retained instead of hidden. That gives a filled numerical-stability envelope rather than a handful of nearly coincident points.

## Quantities computed

### 1. Tight CINDER reference

A single tight CINDER run is used only as the numerical reference:

- LSODA
- `max_step = 0.1 ms`
- `rtol = 1e-10`
- `atol = 1e-12`

This is **not** claimed to be physical truth. It is the high-resolution reference used to ask whether looser solver settings change CINDER's own trajectory.

### 2. Per-signal trajectory errors

For a signal \(q(t)\), the relative RMS difference from the tight reference is

\[
\epsilon_q =
\frac{
\sqrt{\frac{1}{N}\sum_i [q_i-q_{i,\mathrm{ref}}]^2}
}{
\max\!\left(\sqrt{\frac{1}{N}\sum_i q_{i,\mathrm{ref}}^2}, q_{\mathrm{floor}}\right)
}.
\]

The script computes this separately for primary speed, secondary speed and speed ratio. Shift error is normalized by the available physical shift travel:

\[
\epsilon_s =
\frac{\mathrm{RMS}(s-s_{\mathrm{ref}})}{s_{\max}}.
\]

The heat-map score is deliberately conservative:

\[
\epsilon_{\mathrm{comp}}
= \max(\epsilon_{\omega_p},\epsilon_{\omega_s},\epsilon_R,\epsilon_s).
\]

It is displayed in parts per million,

\[
\epsilon_{\mathrm{ppm}} = 10^6\epsilon_{\mathrm{comp}}.
\]

This means one very sensitive state cannot be hidden by averaging it together with several insensitive states.

The script also preserves dimensional errors such as RMS/max primary RPM difference and RMS/max shift difference in micrometres in `stress_sweep.csv`.

### 3. Hybrid-topology stability

Numerical convergence is not just continuous-state closeness in a hybrid model. A numerically bad run could take a different contact/slip/constraint path while ending near a similar final point.

Therefore the script records the complete ordered transition signature

\[
\mathcal{S}=\{(m_k, e_k, r_k)\}_{k=1}^{N_{tr}},
\]

where \(m_k\) is the previous mode, \(e_k\) the fired event set and \(r_k\) the transition reason. It reports whether this signature exactly matches the tight reference.

It also compares sampled mode occupancy using an \(L_1\) difference,

\[
D_{\mathrm{occ}} = \sum_m |p_m-p_{m,\mathrm{ref}}|.
\]

### 4. Actual solver work

The generic CINDER result currently retains hybrid segments and transitions but not SciPy's work counters. The stress-test script temporarily wraps the same `solve_ivp` call and records, without changing the physics:

- `nfev`: RHS evaluations,
- `njev`: Jacobian evaluations,
- `nlu`: LU factorizations,
- accepted internal steps,
- minimum / 5th percentile / median / 95th percentile / maximum accepted \(\Delta t\).

This distinction matters because `max_step` is only an upper bound. The quantity that supports a statement about the time scale LSODA *actually used* is the accepted-step distribution, especially its median or 95th percentile, **not** `max_step` alone.

### 5. Real-time factor

For a five-second simulated interval,

\[
F_{RT} = \frac{T_{sim}}{T_{wall}} = \frac{5\ \mathrm{s}}{T_{wall}}.
\]

Thus:

- \(F_{RT}=1\): real time,
- \(F_{RT}=10\): ten simulated seconds per wall-clock second,
- \(F_{RT}=100\): one hundred simulated seconds per wall-clock second.

Timing excludes construction of the benchmark setup and excludes plotting/sampling. It times the integration itself. Multiple repetitions can be requested; the median is used.

## Ballew reference scales

Ballew reports fixed-step fourth-order Runge-Kutta integration with time steps **on the order of**

\[
h_B \sim 10^{-5}\ \mathrm{s} = 0.01\ \mathrm{ms}.
\]

For a five-second trajectory, the corresponding fixed-step-count scale is

\[
N_B \sim \frac{5}{10^{-5}} = 5\times10^5
\]

or roughly **500,000 fixed time steps**.

A straightforward RK4 method evaluates four stages per step, giving an order-of-magnitude stage-evaluation scale of

\[
N_{RK4} \sim 4N_B \sim 2\times10^6.
\]

This is useful as a **numerical-work scale**, not a direct operation-for-operation comparison: Ballew's distributed belt RHS and CINDER's reduced RHS have very different costs, and Ballew also performs iterative geometry/search work within steps.

The script therefore does **not** call the ratio of Ballew's estimated stage count to CINDER's `nfev` a wall-clock speedup.

## The useful ratios the script can answer after the run

### Allowed-step-scale ratio

If a CINDER point remains converged with maximum permitted step \(h_{max}\),

\[
G_{allowed}=\frac{h_{max}}{h_B}.
\]

This says how much larger the **allowed** step ceiling is. It is visually dramatic but should not be called the actual integration-step ratio.

### Actual accepted-step-scale ratio

Using the 95th percentile accepted CINDER step,

\[
G_{actual,95}=\frac{h_{95,CINDER}}{h_B}.
\]

This is the stronger statement about the numerical time scale the adaptive solver actually used.

### Step-count compression

If CINDER requires \(N_C\) accepted adaptive steps,

\[
C_N = \frac{N_B}{N_C}.
\]

This quantifies how many fewer accepted integration intervals CINDER uses compared with the fixed-step scale implied by Ballew's reported timestep. It remains a step-count comparison, not a CPU-speed comparison.

### CINDER-vs-CINDER speedup

A clean apples-to-apples runtime comparison is available inside CINDER itself. For example, if the nominal setting takes \(T_N\) and the fastest setting still below the chosen error threshold takes \(T_F\),

\[
S_{CINDER}=\frac{T_N}{T_F}.
\]

This is a legitimate measured speedup because the model, machine and benchmark are the same.

## Generated plots

`00_numerical_stability_story.png` is the main four-panel figure. It combines:

1. a filled heat map of trajectory error over `(max_step, rtol)`,
2. the wall-time/accuracy Pareto frontier,
3. RHS work (`nfev`) versus allowed max step, with Ballew's ~2 million RK4-stage scale shown only as an order-of-magnitude reference,
4. the 95th-percentile *actual* accepted CINDER step versus Ballew's ~0.01 ms fixed-step scale.

The separate plots are:

- `01_stability_envelope_heatmap.png`
- `02_speed_accuracy_pareto.png`
- `03_solver_work_vs_max_step.png`
- `04_trajectory_stress_overlay.png`
- `05_actual_internal_step_scale.png`
- `06_method_comparison.png` when `--compare-methods` is requested.

`SUMMARY.md` is generated from the measured results. It automatically identifies the fastest cases below 100 ppm and 1000 ppm, the largest allowed max step that remains strongly converged, the actual step-size ratio to Ballew's scale, the step-count compression, real-time factor and any failure region reached by the sweep.

## What a strong paper claim would look like

After the sweep, the wording can be populated directly from `SUMMARY.md`. The preferred structure is:

> Ballew reported numerical stiffness requiring fixed RK4 steps on the order of 10 µs. In the equivalent five-second closed-loop benchmark, CINDER remained within [measured error] of its tight numerical reference while LSODA accepted 95% of its steps below [measured dt] and required [measured accepted steps / nfev]. The resulting simulation executed at [measured real-time factor]× real time on [machine description].

That is substantially stronger than saying only that CINDER was stable at a larger `max_step`.

## Claims to avoid

Do not state a measured **CINDER-vs-Ballew wall-clock speedup** unless Ballew's executable is run on controlled hardware. The thesis gives enough information to compare timestep scale and infer an approximate fixed-step / RK4-stage workload, but not enough to reconstruct an apples-to-apples runtime.

Likewise, numerical convergence is not physical validation. The Ballew comparison can show agreement or model-form differences; the stress test only establishes that those CINDER conclusions are not artifacts of a fragile integrator setting.
