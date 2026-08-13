# Ballew reconstruction register

Authoritative record of choices not stated directly or not stated unambiguously in Ballew (2015). Code comments reference these IDs where the choices are applied.

The Chapter 5 benchmark is a **simulated vehicle-acceleration case**, not a road or dyno experiment. Ballew prescribes engine torque and pulley clamp-force conditions, while output-shaft resistance comes from the simulated ATV/road-load model. The exact thesis PDF used to define this register is archived at `reference/source/Ballew_2015_thesis.pdf`; the runner verifies its SHA-256 before use.

## A1 — Shaft inertia

**Source:** Table A1 gives `0.008 kg m^2` for input pulley + engine, `0.002 kg m^2` for the output pulley, and `1.275 kg m^2` for output pulley + ATV, without a finer split or a completely explicit statement of how the latter is combined with the separately reported vehicle mass.

**CINDER:** place the full `0.008 kg m^2` on the primary boundary. The CVT assembly carries `0.002 kg m^2` on the output pulley; the secondary boundary supplies the remaining inertia after the published `226 kg` ATV mass is reflected through the stated reduction/tire radius. No separate wheel-spin inertia is invented.

**Why this is an assumption:** the vehicle mass itself is published; the ambiguity is whether Ballew's `1.275 kg m^2` already includes that reflected translation and exactly what additional rotating hardware is contained in the total.

**Sensitivity:** compare alternate interpretations of the `1.275 kg m^2` total after the untouched baseline exists; do not tune the split to Figure 41.

## A2 — Road-load constants not reported

**Source:** Ballew reports ATV mass, tire radius, frontal area, drag coefficient and rolling-resistance coefficient. Air density, gravity and the numerical treatment of rolling-resistance direction at zero speed are not reported.

**CINDER:** explicitly use `rho = 1.225 kg/m^3`, `g = 9.80665 m/s^2`, and CINDER's `0.01 m/s` smooth rolling-direction regularization. These are written into the benchmark case rather than inherited silently from defaults.

## A3 — Initial state: exact RPMs, rounded ratio

**Source:** Table B1 gives input speed `2500 rpm`, output speed `1136 rpm`, and ratio `2.2`. The two speeds imply `2500/1136 = 2.200704...`.

**CINDER:** treat the two explicitly tabulated shaft speeds as authoritative and the stated `2.2` as rounded. Solve the initial engaged geometry so

`r_s,eff / r_p,eff = 2500 / 1136`,

then set the belt speed from the corresponding no-slip belt-line speed. Initial shift rate is zero; Ballew initializes node velocities along the already constructed belt path and has no separate sheave-velocity state.

**No sensitivity required:** the discrepancy is source rounding, not a meaningful physical uncertainty.

## A4 — Equivalent belt section, path datum, and exact 1 kg mass

**Source:** Table A1 gives belt length `0.8636 m` and mass `1 kg`, while Table B1 independently gives 50 nodes at `0.02 kg` each. Ballew's transient algorithm uses a one-dimensional nodal belt path, with initial node spacing `L/n` and node radius used directly in pulley torque calculations. Chapter 4 states that material tests were performed on a Gates G-Force `26C3596` and that a CAD cog/rib profile was created for section-property measurements.

Figure 39 gives a directly dimensioned minimum section used by Ballew for bending inertia: `0.30 in` high, `1.18 in` outer/top width, `1.05 in` inner/bottom width, with the neutral-axis/cord line `0.25 in` above the bottom (`0.05 in` below the outer surface). Ballew explicitly excludes the cog/rib portions from this bending section.

Table A1 also prints `belt width = 0.152 m`; this is inconsistent with Figure 39 and is not used as a physical cross-section dimension.

**CINDER mapping:**

1. Use Figure 39 as an **equivalent smooth load-carrying trapezoid**, not as the literal full cogged envelope.
2. Identify Ballew's one-dimensional nodal path with CINDER's effective/cord-line path. This is the only datum choice needed to bridge Ballew's single-radius belt model to CINDER's separate outer/effective radii.
3. Preserve Ballew's `0.8636 m` at that effective path. With constant cord depth `d`, offset both pulley radii outward by `d`. The open-belt straight spans are unchanged and the wrap angles sum to `2*pi`, so CINDER's outer-surface length is exactly `L_outer = 0.8636 + 2*pi*d`.
4. Select the CINDER density from `rho_eff = 1 kg / (A_equiv L_outer)` so the resolved belt mass is exactly the published `1 kg`.

**Interpretation:** `rho_eff` is a mass-lumping parameter for the equivalent smooth section. It is not interpreted as physical rubber/composite density.

**Geometric endpoints:** Ballew's `0.0159 m` minimum radii are hard pulley/search bounds, not a simultaneously reachable fixed-length endpoint. For CINDER `s=0`, hold the secondary at the published `0.0838 m` maximum effective radius and solve the compatible primary effective radius from Ballew's `L` and `C`. Set `s_max` so the primary reaches its published `0.0838 m` maximum. No deadzone is introduced because Chapter 5 starts already engaged.

**External belt catalogs:** the `26C3596` identity is useful provenance, but commercial/current dimensions are not substituted into the headline baseline when they conflict with Chapter 5's explicit numerical constants.

## A5 — Prescribed clamp force and no movable-sheave axial EOM

**Source:** Ballew's pulley search varies the uncompressed radius until the summed axial compression force from belt nodes equals the applied axial force at the movable-sheave boundary. There is no separately integrated `m_sheave x_ddot` equation. The primary force is controller-generated; the secondary force is fixed at `2000 N`.

**CINDER:** set both literal moving-sheave masses to zero and install no helical coupling. The primary receives the Figure 45 prescribed force history; the secondary receives constant `2000 N`.

In current CINDER, the primary and secondary local axial rows contain only actuator force, the corresponding literal moving-sheave D'Alembert reaction, and belt normal reaction. With zero moving-sheave masses they reduce to the algebraic balances `F_p - N_p/(2 tan(beta)) = 0` and `F_s - N_s/(2 tan(beta)) = 0`. No special Ballew-only dynamics mode or artificial sheave acceleration law is introduced.

**Engagement topology:** Chapter 5 starts with the belt already engaged and Ballew's formulation contains no separate primary deadzone/disengaged interval for this case. CINDER therefore uses `deadzone_shift = lower_stop_shift = 0`, represented explicitly as a **zero-width deadzone / always-engaged topology**. The shared lower boundary is the engaged low-ratio seat. CINDER's general operating-limit contract was extended to allow this physically meaningful equality; in that topology the `PRIMARY_CLAMP_LOST -> deadzone` transition is omitted because no neutral interval exists. This is preferable to inventing a tiny positive deadzone solely for numerical compatibility.

**Important model-form distinction:** the CINDER shift state is still dynamically determined because belt radial/transport inertia appears in the reduced belt compatibility equations. Ballew resolves those dynamics through individual belt nodes. The `1 kg` belt therefore remains fully active in the CINDER benchmark; only nonexistent sheave axial inertia is removed.

## A6 — Figure 45 force replay and zero-time support

**Source:** the undamped primary axial-force history is published graphically in Figure 45; the exact controller implementation is not fully specified. The manually digitized visible curve contains 211 points from `t = 0.095541... s` through `5.0 s`. The WebPlotDigitizer project and raw headerless CSV are preserved under `reference/digitization/`.

**Force-replay benchmark:** replay the prepared Figure 45 trace piecewise-linearly as prescribed primary closing force. This remains the plant-forced-response comparison: both models are asked what they do under the same external force history.

**Closed-loop benchmark:** Figure 45 is instead reserved as a controller-output reference. The source-constrained controller reconstruction is documented separately in A11. Neither benchmark is treated as uniquely "the" correct comparison; they answer different questions.

The raw digitization contains four exact duplicate time coordinates (`0.477707`, `2.468153`, `3.789809`, and `4.490446 s`) from near-vertical segments clicked twice in one pixel column. The preparation script replaces each duplicate-time group with the arithmetic mean force so the replay remains a single-valued function; the raw source is not modified.

Figure 45 itself does not draw the force curve all the way to `t=0`, but the CINDER input must be defined at the initial state. The prepared replay therefore adds `F_p(0)` by holding the first visible digitized force (`2182.547... N` at `0.095541... s`) backward over that short initial interval. This zero-order hold is preferred to inventing an unsupported extrapolation slope and is a small explicit benchmark-boundary assumption.

No smoothing, resampling, filtering, or controller reconstruction is applied.

## A7 — Figure 41 reference response

**Source:** undamped primary/output pulley speed histories are published graphically in Figure 41. The raw WebPlotDigitizer bundle contains 113 input-RPM points and 64 output-RPM points, both spanning approximately `0.110375-4.988962 s`.

**Comparison:** preserve the two traces on their native digitized time grids and compare CINDER primary RPM at the input trace times and CINDER secondary RPM at the output trace times. The runner retains solver-native dense output and evaluates CINDER directly at those exact timestamps. The headline primary/secondary errors therefore do not resample either paper trace. The derived ratio uses the sorted union of the two visible Figure 41 time sets; each reference trace is linearly interpolated only to timestamps belonging to the other reference trace. The archived raw data are never changed.

The graph does not visibly extend to `t=0`, so no artificial zero-time reference point is added. Table B1 supplies the exact CINDER initial shaft states (`2500 rpm`, `1136 rpm`); Figure 41 is used only where the published curves are visible.

Both project JSON files and all raw CSV exports are retained under `reference/digitization/` so the calibration and clicked points can be independently reopened and checked.

## A8 — Ballew-only distributed belt and near-zero friction details

Ballew begins Chapter 5 with zero longitudinal belt tension and reports node stiffness/damping plus a `0.02 m/s` minimum relative velocity for stuck friction. Section 3.5 makes the latter more specific: for each compressed node, `|v_rel| >= v_min` uses kinetic Coulomb friction `mu_d F_z`; below `v_min`, the node either exactly cancels its other tangential force when that demand is below `mu_s F_z`, or enters Ballew's "impending motion" branch at the static limit `mu_s F_z`. Thus Ballew has a finite near-zero friction layer rather than CINDER's exact gross-contact stick/slip event at `v_rel = 0`.

CINDER has no one-to-one distributed states/parameters for those node laws. Retain the values in `constants.py` for provenance and do **not** silently map `0.02 m/s` to CINDER's gross-contact switching tolerance. If the benchmark exposes a zero-crossing incompatibility, first inspect the CINDER candidate modes and only then decide whether a documented Ballew-specific friction sensitivity is warranted. Figures 41/45 use the *undamped* branch.

The inability to reproduce Ballew's exact zero-tension internal nodal state is a structural initialization difference and should be discussed with the eventual results rather than hidden by tuning.

## A9 — Meaning of `Transmission Ratio = 8.93`

**Source:** Table A1 reports `Transmission Ratio = 8.93` beside the ATV/tire data without a more specific label.

**CINDER:** interpret it as the fixed reduction between CVT output and wheel for vehicle kinematics, road-load torque and inertia reflection.

**Why this matters:** Ballew's output load is not a prescribed brake torque; it is generated by the simulated vehicle through this downstream mapping. An incorrect interpretation of `8.93` changes both reflected inertia and road-load torque.

**Status:** keep the interpretation explicit until confirmed from Ballew's vehicle equations/implementation or another source.

## A10 — Ballew friction coefficient versus CINDER traction utilization

**Source:** Table A1 publishes `mu_s = 0.55` and `mu_k = 0.40`. In Ballew's node model, Section 3.3 defines node axial compression force `F_Z` and the corresponding in-plane radial reaction `F_R = 2 F_Z tan(alpha)`. Section 3.5 then applies the published Coulomb values to `F_Z`: kinetic friction magnitude is `mu_k F_Z`, with the static/impending limit `mu_s F_Z`. The pulley search enforces that the sum of the node `F_Z` values equals the applied clamp force.

**CINDER convention:** CINDER's engaged-contact closure uses the reduced traction utilization

`lambda = Q / N = tau / (r_tau N)`,

where the zero-sheave-mass clamp row gives the in-plane normal/radial resultant `N = 2 F_clamp tan(beta)`. The fields currently named `*_friction_coefficient` are passed directly into CINDER's internal signed lambda limits.

To preserve Ballew's **gross tangential capacity** under the reduced contact convention, the benchmark therefore maps

`lambda = mu / (2 tan(beta))`.

At Ballew's `beta = 15 deg`, this gives

- `lambda_s = 1.026313972081...`;
- `lambda_k = 0.746410161514...`.

The published `0.55/0.40` values remain stored verbatim in `PUBLISHED`; the derived values exist only in the benchmark translation layer. They are **not** reinterpreted as material Coulomb coefficients, and they do not make CINDER's one-resultant contact law equivalent to Ballew's two-dimensional per-node friction vector. This is a convention/capacity translation, not a fitted correction.

**Numerical note:** changing the kinetic lambda magnitude changes CINDER's hybrid slip branches and exposed a pre-existing geometry/topology bug at the low-ratio engagement boundary. The v9 corrected replay reached an exact rank-7 both-slip matrix because an engaged event-localization stage projected to `s = deadzone_shift` was evaluated with the *deadzone-side* radius derivatives (`dr/ds = 0`). With zero Ballew sheave masses that removed the only remaining `s_ddot` coefficient. The core geometry now supplies explicit engaged-side one-sided derivatives at the shared boundary; no friction or shift physics was changed. See `SINGULARITY_DIAGNOSIS.md` and A12.

## A11 — Primary PI + feed-forward controller reconstruction

**Published by Ballew:** Chapter 5 states that a PI controller with feed-forward gain actuates the primary axial force to maintain a fixed input speed during the simulated upshift. Table B1 gives `K_ff = 1.2`, `K_P = 5`, `K_I = 75`, initial/target input speed `2500 rpm`, and fixed secondary clamp `2000 N`. Ballew also explains the sign qualitatively: when the initially zero-tension belt causes the input pulley to decelerate, the PI controller **reduces** primary axial force so the input speed can recover. Figure 45 is therefore a controller output, not an independently prescribed physical input in Ballew's original closed-loop simulation.

**Not published:** the thesis does not provide the explicit controller algebraic equation, the quantity multiplied by the dimensionless feed-forward gain, the initial integrator state/controller bias, or any output saturation/anti-windup implementation. No supplemental controller code was found in the archived thesis material.

**Sign and units inferred without fitting gains:** the digitized Figure 41 primary-RPM trace and Figure 45 force trace can test the *change* in a standard PI output. For

`F_p = C + K_P e + K_I integral(e dt)`,

subtracting the value at the first common visible time removes the unknown constant `C` (feed-forward plus any prior integrator bias). Using the published `K_P=5`, `K_I=75`, the four natural interpretations give approximately:

- `e = n_p - 2500` in RPM: **52.65 N** force-change RMSE;
- same sign in rad/s: **377.5 N**;
- opposite sign in RPM: **822.6 N**;
- opposite sign in rad/s: **461.6 N**.

As a secondary consistency check only, fitting the two published PI coefficients to force *changes* gives approximately `K_P=5.61`, `K_I=63.3`; holding the published `K_P=5` gives `K_I=72.97`, close to the published `75`. These diagnostic fits are never used as benchmark inputs. The source statement that force decreases when speed is below target independently supports the measured-minus-target sign.

**Headline source-constrained reconstruction:**

`e = n_p[rpm] - 2500`,

`I_dot = e`,

`F_p = 1.2(2000 N) + 5 e + 75 I`.

Thus the feed-forward force is reconstructed as `2400 N`. The interpretation `K_ff * F_s` is the simplest source-native use of the only fixed clamp scale Ballew publishes, but it remains an explicit inference. The initial integral is set to zero because no initial bias is published. No saturation or anti-windup is invented. `controller_reconstruction.py` reproduces the offset-free trace audit and records these source gaps.

The controller integral is a host ODE state around the unchanged CINDER plant; no CINDER physical state/equation is modified. `run_closed_loop_comparison.py` uses Figure 41 and Figure 45 only as outputs for comparison. If the same source-constrained controller is incompatible with CINDER's faster shift/contact dynamics, that is a benchmark result rather than a reason to retune gains or alter CINDER.


## A12 — Engaged-side geometry at the low-ratio hybrid boundary

**Status: resolved numerical/topology defect; not a Ballew calibration.**

The corrected A10 traction translation drove the force-replay and controller cases through the low-ratio boundary aggressively enough to expose a singular free both-slip closure. Instrumentation showed that LSODA was evaluating a normal out-of-domain trial stage while bracketing `LOW_RATIO_SEAT_REACHED`. The engaged evaluator correctly projected geometry for that rejected stage to `s = 0`, but the geometry accessor used the deadzone-side derivative convention at equality. Because Ballew has `deadzone_shift = 0`, this returned `dr_p/ds = dr_s/ds = 0` instead of the engaged-side limit. With both moving-sheave masses set to zero, the free closure then had an identically zero `s_ddot` column and rank seven.

The correction is regime-aware one-sided geometry, not an epsilon displacement and not a new physical term. `BeltPulleyGeometry.evaluate()` retains deadzone-side derivatives at the kink; `evaluate_engaged()` returns the same positions with engaged-side derivatives; the engaged `MechanicalCVTPlant` snapshot uses the latter while the separate deadzone snapshot keeps the former. This also makes low-seat release into free engagement well-defined at the exact boundary.

At the exact previously failing trial state, the old matrix had `rank=7`, `cond ~= 2.43e18`, and right null direction purely in `s_ddot`. With engaged-side derivatives the same trial has `rank=8`, `cond ~= 5.38e3`, and a finite tension-loop `s_ddot` coefficient of about `-0.41875`. Both the force-replay and reconstructed-controller cases pass their former early singularities and have been stress-integrated to at least one second. See `SINGULARITY_DIAGNOSIS.md` for the reproduced matrix-level diagnosis.

## Comparison protocol — implementation choice, not a reconstruction assumption

The numerical comparison itself does not introduce another physical reconstruction
assumption. The default headline run uses CINDER's standard composed hybrid
integrator for `0-5 s` with LSODA, `rtol=1e-7`, `atol=1e-9`, `max_step=1e-3 s`,
and retained solver-native dense output. These controls are deliberately tighter
than the ordinary fast vehicle-study defaults so numerical error is small compared
with the digitization/model-form differences. They remain command-line options and
should later be convergence-tested.

Primary and secondary RPM metrics are evaluated only at the native Figure 41
digitized timestamps. The uniform `cinder_trace.csv` grid exists for diagnostics
and plotting; it is **not** the metric grid. Reported errors are signed mean error,
MAE, RMSE, maximum absolute error, and RMSE as a percentage of mean absolute
reference value. No reconstruction parameter is adjusted based on these errors.

Hybrid mode/contact history and transitions are saved alongside the comparison so
a discrepancy can be traced to CINDER's physical regime changes rather than hidden
in a single aggregate score.
