# Stress-test result package

## Why this study exists

The Ballew closed-loop comparison produces unusually rapid internal shift motion and a very dense hybrid-event history. The purpose of this stress test is to determine whether the approximately 3--5% CINDER--Ballew shaft-speed/ratio discrepancy, the substantially different clamp-force demand, or the violent internal CINDER shift motion could plausibly be integration artifacts.

The answer is **no** over the solver-control region relevant to the benchmark. The macroscopic CINDER trajectory is strongly numerically converged, and the broader sweep shows a wide plateau of numerical insensitivity before coarse tolerances begin to produce physically meaningful drift.

This note is the canonical interpretation of the stress-test outputs. Wall-clock timing was collected by the harness but is **not used as a headline result or as a CINDER-vs-Ballew speed claim**.

## Stress-test scope

The sweep varies LSODA relative tolerance and the permitted maximum integration step over several orders of magnitude while holding all physical parameters, controller parameters, initial conditions, and reporting definitions fixed.

The tight numerical reference uses `rtol = 1e-10`, `atol = 1e-12`. The broad sweep contains **72/72 successful five-second integrations**; no tested case failed to reach the endpoint.

`max_step` is only an upper bound. CINDER uses adaptive LSODA, so the actual accepted step sizes are reported separately and are the more meaningful comparison with Ballew's fixed-step integration scale.

## Composite trajectory-error definition

For each reported state/output quantity, the stress-test harness computes a normalized RMS difference relative to the tight reference. The composite error is the maximum of the primary-speed, secondary-speed, speed-ratio, and normalized-shift errors:

\[
\epsilon_{\mathrm{comp}}
=\max\!\left(
\epsilon_{\omega_p},
\epsilon_{\omega_s},
\epsilon_R,
\epsilon_s
\right).
\]

The figures report this quantity in parts per million,

\[
\epsilon_{\mathrm{ppm}}=10^6\epsilon_{\mathrm{comp}}.
\]

Thus 100 ppm corresponds to 0.01%, and 1000 ppm corresponds to 0.1%.

## Main convergence result

At the nominal closed-loop benchmark tolerance, `rtol = 1e-7`, the solution differs from the tight reference by only about **21.45 ppm = 0.00215%** once `max_step` is no longer the active limitation. The corresponding RMS physical differences are only:

- primary speed: **0.00743 rpm**;
- secondary speed: **9.69e-05 rpm**;
- speed ratio: **6.35e-06**;
- shift coordinate: **0.577 um**.

The maximum primary-speed difference is only **0.0194 rpm**, the maximum ratio difference **1.64e-05**, and the maximum shift difference **2.09 um**.

These errors are microscopic relative to the actual five-second motion and to the approximately **5.24%** CINDER--Ballew speed-ratio RMSE. The model-to-model discrepancy is therefore roughly thousands of times larger than the integration-error scale at the nominal settings.

## Broad accuracy plateau and graceful degradation

A major result of the wider sweep is that the solution becomes almost independent of the imposed `max_step` once the bound is above roughly the millisecond scale. Beyond that point LSODA chooses its own smaller internal steps as required by the dynamics and hybrid events. Increasing the permitted `max_step` to tens or hundreds of milliseconds therefore does **not** imply that the solver actually integrates through the difficult portions of the trajectory using such large steps.

At `max_step >= 3 ms`, representative tolerance results are:

| Relative tolerance | Composite error | Primary RMS drift | Ratio RMS drift | Shift RMS drift | Accepted steps |
|---:|---:|---:|---:|---:|---:|
| 1e-7 | 21.45 ppm = 0.00215% | 0.00743 rpm | 6.35e-06 | 0.577 um | 31,815 |
| 1e-5 | 244.95 ppm = 0.0245% | 0.08597 rpm | 7.35e-05 | 6.58 um | 19,263 |
| 1e-4 | 3604.68 ppm = 0.360% | 1.240 rpm | 1.06e-03 | 96.9 um | 14,393 |
| 1e-3 | 53,293 ppm = 5.33% | 18.11 rpm | 1.55e-02 | 1.432 mm | 10,773 |

This is a useful numerical story: CINDER exhibits a **large converged region followed by progressive degradation**, rather than an abrupt loss of integration stability. `rtol = 1e-5` remains extremely close to the tight reference; `1e-4` produces visible but still sub-percent drift; and `1e-3` is coarse enough that the numerical error becomes comparable to the model-to-model discrepancy and should not be used for the benchmark.

## Hybrid-event stability: substantive physics versus bookkeeping

The raw transition signature is intentionally not used as a binary convergence criterion because one event type is tolerance-sensitive bookkeeping around `v_rel = 0`:

`kinetic_slip_direction_updated_at_zero_crossing`

At `max_step = 1 ms`, the event decomposition is:

| Relative tolerance | Raw transitions | Kinetic direction zero-crossing updates | Substantive transitions |
|---:|---:|---:|---:|
| 1e-10 | 1412 | 1 | **1411** |
| 1e-7 | 1629 | 218 | **1411** |
| 1e-6 | 1831 | 420 | **1411** |
| 1e-5 | 1622 | 211 | **1411** |
| 1e-4 | 1622 | 211 | **1411** |
| 1e-3 | 1628 | 211 | **1417** |

The substantive topology therefore remains **exactly 1411 transitions through `rtol = 1e-4`** for the nominal 1 ms step bound, despite large changes in the number of recorded kinetic-direction updates. The first clear substantive-topology drift in this sequence appears only at the deliberately coarse `rtol = 1e-3` case, consistent with the simultaneous growth in trajectory error.

The 1411 substantive transitions themselves are highly structured and repeatable in the converged runs:

- 419 simultaneous contact-topology exchanges at a zero crossing;
- 359 successful re-sticks with static reserve;
- 213 static-capacity exits into kinetic slip;
- 210 low-ratio-seat impacts with perfectly inelastic projection;
- 149 low-ratio-seat releases by tensile reaction;
- 61 contact transitions that simultaneously release the low-ratio seat.

Accordingly, the exact raw transition total should **not** be reported as a count of physical events. Reports should separate substantive contact/constraint transitions from kinetic slip-direction zero-crossing updates.

## Adaptive timestep scale relative to Ballew

Ballew reports using fixed fourth-order Runge--Kutta time steps on the order of

\[
h_B \sim 10^{-5}\ \mathrm{s}=0.01\ \mathrm{ms}
\]

because the distributed-belt equations were numerically stiff and could become unstable at larger fixed steps.

For the nominal CINDER tolerance (`rtol = 1e-7`) once the maximum-step bound is no longer limiting, the actual accepted adaptive-step distribution is approximately:

- median accepted step: **0.0914 ms**, about **9.1x** Ballew's reported fixed-step scale;
- 95th-percentile accepted step: **0.4656 ms**, about **46.6x** Ballew's reported fixed-step scale;
- maximum accepted step in the 300 ms-bound case: **1.175 ms**.

CINDER still contracts to much smaller steps locally around difficult hybrid events. This is the intended advantage of adaptive event-driven integration: fine resolution is applied where the dynamics require it rather than imposing Ballew's globally tiny fixed-step scale throughout the entire five-second trajectory.

At `rtol = 1e-5`, which still has only about **0.0245%** composite trajectory error, the median and 95th-percentile accepted steps increase to approximately **0.154 ms** and **0.755 ms**, respectively.

## Integration-work scale relative to Ballew

A fixed `0.01 ms` step over a five-second simulation corresponds to the order-of-magnitude scale

\[
N_B \approx \frac{5}{10^{-5}} = 500{,}000\ \text{fixed steps}.
\]

CINDER requires approximately:

- **31,815 accepted adaptive steps** at `rtol = 1e-7`, about **15.7x fewer** integration steps than the Ballew fixed-step scale;
- **19,263 accepted adaptive steps** at `rtol = 1e-5`, about **26.0x fewer**, while remaining within about **0.0245%** of the tight CINDER reference.

These are **integration-step/work-scale comparisons**, not wall-clock speedup claims. The original Ballew implementation was not benchmarked on the same hardware, and the computational cost of one Ballew RK4 stage is not equivalent to one CINDER RHS evaluation.

## Why this is a particularly demanding CINDER case

The reconstructed Ballew closed-loop trajectory contains **1411 substantive hybrid transitions in five seconds**, or roughly **282 substantive transitions per simulated second**. Each terminal hybrid event can end the active continuous-integration segment, resolve a contact/constraint transition, and begin a new segment.

The Ballew reconstruction is therefore unusually event-dense because of its rapid internal shift/contact oscillation. It is reasonable to expect a smoother nominal launch or shift to contain substantially fewer hybrid restarts and to permit longer continuous integration intervals and larger adaptive steps. That expectation follows directly from the event-driven solver structure, but it should be benchmarked separately before being turned into a quantitative runtime or speed claim.

## Interpretation for the paper

The useful comparison is **not** "CINDER is X times faster than Ballew." The stronger, directly supported numerical result is:

> **Ballew's distributed formulation required a globally small fixed timestep on the order of 10 us for numerical stability. CINDER's reduced hybrid formulation remains macroscopically converged across a broad solver-control region and uses adaptive integration that locally contracts around difficult events while accepting substantially larger steps elsewhere. Even in the unusually event-dense Ballew reconstruction, the nominal CINDER trajectory requires roughly sixteen times fewer accepted integration steps than the fixed-step scale implied by Ballew's reported timestep.**

This result strengthens the main comparison conclusion. The approximately 3--5% shaft-speed/ratio discrepancy, substantially different clamp-force requirement, and more violent CINDER internal shift motion survive numerical refinement by margins far larger than the integration error. They should therefore be interpreted primarily as **model-form differences**, not integration artifacts.

## Canonical figures and data

- `01_stability_envelope_heatmap.png` — trajectory error over the broad `max_step`/tolerance space.
- `04_trajectory_stress_overlay.png` — physical trajectory drift as controls are deliberately coarsened.
- `05_actual_internal_step_scale.png` — actual accepted LSODA step sizes relative to Ballew's reported fixed-step scale.
- `06_adaptive_step_count_vs_tolerance.png` — accepted adaptive integration steps versus tolerance, with the approximate Ballew five-second fixed-step count for context.
- `07_transition_decomposition_vs_tolerance.png` — substantive topology transitions separated from kinetic-direction zero-crossing bookkeeping.
- `stress_sweep.csv` — compact numerical results for all 72 cases.
- `raw_results.jsonl` — full run records including transition signatures and mode occupancy.
- `reference_and_literature_scales.json` — numerical reference definitions and Ballew step scale.
- `AUTO_SUMMARY_ORIGINAL.md` — original harness-generated summary retained for provenance; its wall-clock discussion is not part of the canonical paper interpretation.
