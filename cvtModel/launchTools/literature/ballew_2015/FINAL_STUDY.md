# Final CINDER–Ballew 2015 comparison study

## Purpose

This directory is the canonical, self-contained CINDER comparison against Brian G. Ballew's 2015 discretized rubber-belt CVT simulation. It is a **model-to-model benchmark**, not an experimental validation. The comparison deliberately retains the physical and numerical differences between the two formulations rather than tuning CINDER to Ballew's published curves.

The study uses two complementary protocols and a numerical-convergence audit:

1. **Force replay** — Ballew Figure 45 primary clamp force is imposed on CINDER and the resulting shaft speeds/ratio are compared with Figure 41.
2. **Closed loop** — Ballew's published PI + feed-forward controller is reconstructed around unchanged CINDER; shaft speeds, ratio, and the controller-generated primary clamp force are all compared with Ballew.
3. **Closed-loop convergence study** — all physics/controller inputs are frozen while maximum integration step and LSODA tolerances are refined.

These three pieces should be interpreted together.

## Headline results

| Protocol | Primary RPM RMSE | Secondary RPM RMSE | Speed-ratio RMSE | Primary-force RMSE |
|---|---:|---:|---:|---:|
| Force replay | 1796.1 rpm (71.88%) | 38.3 rpm (3.19%) | 1.4513 (69.61%) | imposed input |
| Closed loop | 109.7 rpm (4.39%) | 32.9 rpm (2.74%) | 0.1093 (5.24%) | 1180.2 N (46.04%) |

In the closed-loop run, mean CINDER primary clamp demand is **1517.29 N**, versus **2563.68 N** for the digitized Ballew Figure 45 trace. Thus the macroscopic speed trajectory agrees substantially better than the force required to create it.

## What the two protocols mean

### 1. Force replay: the plants are not dynamically equivalent

Applying the same Ballew primary clamp history to CINDER produces very poor primary-speed and speed-ratio agreement: about **71.9%** and **69.6%** RMSE relative to the reference means. Secondary speed remains much closer at about **3.2%**.

This is strong evidence that Ballew's distributed belt/contact model and CINDER's reduced global-shift model do **not** map clamp force into shift motion in the same way. The force-replay result should therefore not be presented as a failed numerical reproduction of the same plant; it is a deliberate test showing model-form sensitivity to an identical force input.

### 2. Closed loop: macroscopic controlled response is similar despite different force demand

Using Ballew's reconstructed PI + feed-forward controller without fitting controller gains or CINDER physics gives approximately:

- **4.39%** primary-speed RMSE;
- **2.74%** secondary-speed RMSE;
- **5.24%** speed-ratio RMSE;
- **46.04%** primary clamp-force RMSE.

This is the main comparison result. The two models can produce a broadly similar controlled shaft-speed/ratio evolution while requiring radically different clamp-force histories and exhibiting different internal shift/contact dynamics.

The result is physically plausible because Ballew distributes radial migration, local friction, belt deformation, bending, contact and damping across many belt nodes, while CINDER collapses the belt/sheave migration into a much more synchronous global shift coordinate and reduced contact law. Agreement in closed-loop speed therefore does not imply agreement in internal force-to-shift mechanics.

## Numerical convergence

Four closed-loop cases were run with every physical and controller input fixed:

| Case | Primary RMSE (rpm) | Secondary RMSE (rpm) | Ratio RMSE | Force RMSE (N) | Raw transitions |
|---|---:|---:|---:|---:|---:|
| 1.00 ms | 109.6651 | 32.92155 | 0.1092994 | 1180.2276 | 1629 |
| 0.50 ms | 109.6651 | 32.92155 | 0.1092994 | 1180.2274 | 1629 |
| 0.25 ms | 109.6650 | 32.92155 | 0.1092994 | 1180.2271 | 1597 |
| 0.50 ms, tighter tol | 109.6649 | 32.92154 | 0.1092994 | 1180.2267 | 1415 |

The largest change across the sweep is only **0.000226%** in primary RPM RMSE, **0.000011%** in ratio RMSE, and **0.000076%** in force RMSE. Mean CINDER clamp force remains essentially fixed near **1517.29 N**.

Comparing the tightest-tolerance case with the original 1 ms run over the common 25,001-point reporting grid gives:

- RMS primary-speed difference: **0.005 rpm**;
- maximum primary-speed difference: **0.011 rpm**;
- maximum speed-ratio difference: **9.52e-06**;
- maximum shift-coordinate difference: **1.226 µm**.

The latter is microscopic relative to the roughly **24.6 mm** shift excursion. The macroscopic closed-loop solution is therefore strongly numerically converged.

## Hybrid-event convergence and the transition-count caveat

The raw transition totals change from **1629** to **1415** as numerical controls are tightened, but this does **not** represent a change in the substantive hybrid trajectory.

Every run contains exactly **1411 substantive contact/constraint transitions**. The entire variation in the raw total is due to `kinetic_slip_direction_updated_at_zero_crossing`, whose count changes 218 → 218 → 186 → 4.

The substantive event counts are otherwise identical, including re-sticks, static-capacity exits, low-ratio-seat impacts/releases, and simultaneous contact-topology exchanges. Compact mode occupancy is also identical to the displayed precision across all four runs; the dominant modes are approximately **65.645% free/both-slip**, **20.111% free/primary-slip-secondary-stick**, and **13.579% low-ratio-seat/both-slip**.

Accordingly, the exact raw number of kinetic slip-direction zero-crossing updates should **not** be reported as a count of physical transitions. It is tolerance-sensitive event bookkeeping around `v_rel = 0`. Reports should distinguish substantive topology/constraint transitions from kinetic-direction zero-crossing updates.

## Numerical stability relative to Ballew's reported integration scale

Ballew explicitly identifies numerical stiffness as a limitation of the distributed-belt algorithm. In Section 3.8 of the archived thesis, the implementation is described as a fourth-order fixed-step Runge-Kutta scheme; unusually small steps were required for stability, with the steps used reported to be on the order of **1e-5 s (about 0.01 ms)**. Ballew further recommends future scaled/variable stepping in part to reduce simulation time.

The CINDER convergence sweep spans `max_step = 0.25--1.00 ms`, or **25--100 times** that reported Ballew fixed-step scale, while the headline closed-loop errors change by at most `0.000226%`. `results/numerical_stability/numerical_stability_envelope.png` visualizes this separation.

This comparison is intentionally phrased as a **numerical operating-scale/convergence result**, not a direct solver-step or wall-clock speedup. CINDER uses adaptive LSODA, so `max_step` is an upper bound and its accepted internal steps may be smaller around events. The original Ballew code has also not been benchmarked on the same hardware and runtime. A direct claim such as “CINDER is X times faster than Ballew” is therefore not supported by the archived comparison.


## Broad numerical-stability stress test

The four-case refinement above was followed by a much wider LSODA stress test spanning several orders of magnitude in `max_step` and tolerance. All **72/72** tested five-second cases completed. The purpose of this sweep is not runtime benchmarking; it maps the numerical operating envelope and determines where trajectory and hybrid-topology errors actually become important.

At the nominal benchmark tolerance (`rtol = 1e-7`), once `max_step` is no longer actively limiting the adaptive solver, CINDER differs from the tight reference by only **21.45 ppm = 0.00215%** composite trajectory error. The associated RMS differences are only **0.00743 rpm** primary speed, **6.35e-06** speed ratio, and **0.577 um** shift coordinate.

The sweep shows a broad convergence plateau. At `rtol = 1e-5`, composite error remains only **0.0245%**. It rises to about **0.360%** at `1e-4` and approximately **5.33%** at `1e-3`. Numerical degradation is therefore progressive rather than an abrupt integration instability.

The raw transition count remains unsuitable as a physical convergence metric because kinetic slip-direction updates around `v_rel = 0` are tolerance-sensitive. Through `rtol = 1e-4` at the nominal 1 ms step bound, every run still contains exactly **1411 substantive contact/constraint transitions**. The deliberately coarse `rtol = 1e-3` case is the first in that sequence to change the substantive topology, increasing it to 1417 while simultaneously producing model-scale trajectory error.

The adaptive-step distribution provides the cleanest numerical comparison with Ballew's reported ~0.01 ms fixed-step scale. At `rtol = 1e-7`, CINDER's actual accepted median step is approximately **0.0914 ms (9.1x Ballew's scale)** and the 95th percentile is approximately **0.4656 ms (46.6x)**. A five-second simulation at Ballew's reported fixed-step scale implies roughly **500,000 fixed steps**; the equivalent converged CINDER case uses about **31,815 accepted adaptive steps**, approximately **15.7x fewer**. At `rtol = 1e-5`, which is still within about 0.0245% of the tight reference, CINDER uses about **19,263 accepted steps**, approximately **26x fewer**.

These are integration-step/work-scale comparisons, **not wall-clock speedup claims**. The original Ballew executable has not been benchmarked on the same machine, and the computational cost per integration stage differs between the formulations.

This Ballew reconstruction is also unusually demanding for CINDER: the 1411 substantive transitions correspond to roughly **282 hybrid transitions per simulated second**. Each terminal event can terminate and restart a continuous integration segment. Smoother nominal CINDER launch/shift cases should therefore be expected to contain fewer restarts and permit longer adaptive intervals, but that expectation should be benchmarked separately before being stated quantitatively.

The canonical interpretation and figures are in `NUMERICAL_STABILITY_RESULTS.md` and `results/numerical_stability/stress_test/`.

## Defensible conclusion

> **The macroscopic closed-loop response is numerically converged. CINDER reproduces Ballew's controlled shaft-speed and speed-ratio evolution to roughly 3–5%, despite predicting substantially different clamp-force requirements and much more rapid internal shift dynamics. The remaining discrepancy is therefore dominated by model-form differences rather than integration resolution.**

The force-replay result reinforces that interpretation: when both models are given the same clamp-force history, their primary-speed and ratio responses diverge strongly. Feedback can place the two systems on similar operating trajectories, but it does so through different force-to-shift mechanics.

This is encouraging evidence for CINDER's **macroscopic closed-loop behavior**, not proof that its internal clamp force, radial migration, local belt deformation, contact mechanics, or shift-rate history reproduces Ballew's distributed belt model.

## What should and should not be claimed

**Supported by this study:**

- CINDER's five-second closed-loop speed/ratio comparison is stable to a 4× maximum-step refinement and tighter LSODA tolerances.
- The broader stress sweep shows a wide convergence plateau; nominal `rtol = 1e-7` differs from the tight CINDER reference by only about 0.00215% composite trajectory error.
- CINDER uses adaptive steps substantially larger than Ballew's reported ~0.01 ms fixed-step scale away from difficult events: at nominal tolerance the median accepted step is about 9.1x larger and the 95th-percentile step about 46.6x larger.
- The nominal converged Ballew reconstruction uses about 31,815 accepted adaptive steps over five seconds versus an order-of-magnitude 500,000 fixed steps implied by Ballew's reported step scale; this is a work-scale comparison, not a wall-clock speedup.
- The reconstructed Ballew controller produces approximately 3–5% shaft-speed/ratio RMSE on unchanged CINDER.
- Clamp-force demand differs substantially: about 46% RMSE, with CINDER's mean demand around 1.52 kN versus Ballew's roughly 2.56 kN digitized mean.
- The poor force-replay result demonstrates a genuine force-to-shift model-form difference.
- Dominant hybrid-mode occupancy and substantive contact/constraint transition counts are numerically stable.

**Not supported / should not be claimed:**

- That Figure 41 or Figure 45 are experimental validation data; they are Ballew simulation outputs.
- That CINDER reproduces Ballew's internal belt-node mechanics.
- That the exact raw transition count is a physical observable.
- That controller or physical parameters were fitted to obtain the closed-loop agreement.
- That 3–5% closed-loop speed agreement validates clamp-force prediction.
- That any step-count or accepted-step-scale separation is itself a wall-clock speedup; the solvers and per-step computational work are not directly equivalent.

## Canonical files

- `README.md` — benchmark reconstruction, assumptions, source provenance, and run instructions.
- `RECONSTRUCTION.md` — every ambiguous/non-published bridge into CINDER.
- `reference/` — thesis PDF, WebPlotDigitizer source data/projects, prepared reference CSVs.
- `results/force_replay/` — identical-force-input comparison and full raw outputs.
- `results/closed_loop/` — reconstructed-controller comparison and full raw outputs.
- `results/convergence/` — four-case solver refinement study, plots, event decomposition, and occupancy data.
- `NUMERICAL_STABILITY_RESULTS.md` — canonical interpretation of the broad solver stress test.
- `results/numerical_stability/` — original four-case stability figure plus the full stress-test data/figures.
- `results/headline_metrics.csv` — compact machine-readable comparison of the main errors.
- `SINGULARITY_DIAGNOSIS.md` and `results/legacy_boundary_derivative_bug/` — provenance for the benchmark-driven hybrid-boundary corrections; these are not canonical physical comparison results.

## Reproduction

From `cvtModel/`:

```powershell
python launchTools/literature/ballew_2015/run_comparison.py
python launchTools/literature/ballew_2015/controller_reconstruction.py
python launchTools/literature/ballew_2015/run_closed_loop_comparison.py
python launchTools/literature/ballew_2015/plot_numerical_stability.py
# Broad numerical stress test (solver controls only; no model changes):
python launchTools/literature/ballew_2015/run_numerical_stability_stress_test.py --preset full
```

The archived convergence outputs are included as the final numerical audit. The convergence study changed only solver controls; no model or controller parameter was altered.
