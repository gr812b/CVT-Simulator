# Ballew reconstruction register

Authoritative record of choices not stated directly or not stated unambiguously in Ballew (2015). Code comments reference these IDs where the choices are applied.

The Chapter 5 benchmark is a **simulated vehicle-acceleration case**, not a road or dyno experiment. Ballew prescribes engine torque and pulley clamp-force conditions, while output-shaft resistance comes from the simulated ATV/road-load model.

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

**Important model-form distinction:** the CINDER shift state is still dynamically determined because belt radial/transport inertia appears in the reduced belt compatibility equations. Ballew resolves those dynamics through individual belt nodes. The `1 kg` belt therefore remains fully active in the CINDER benchmark; only nonexistent sheave axial inertia is removed.

## A6 — Figure 45 force replay

**Source:** the undamped primary axial-force history is published graphically in Figure 45; the exact controller implementation is not fully specified.

**CINDER:** digitize Figure 45 and replay it piecewise-linearly as prescribed primary closing force. Do not tune/reconstruct the controller for the headline comparison. The input CSV must cover the entire `0–5 s` simulation interval so the actuator never extrapolates.

## A7 — Figure 41 reference response

**Source:** undamped primary/output pulley speed histories are published graphically in Figure 41.

**Comparison:** digitize both traces and compare primary RPM, secondary RPM and derived ratio. Store digitization provenance/uncertainty with the CSVs. Table B1, not plot pixels, supplies the exact initial RPMs.

## A8 — Ballew-only distributed belt details

Ballew begins Chapter 5 with zero longitudinal belt tension and reports node stiffness/damping plus a `0.02 m/s` stuck-friction threshold. CINDER has no one-to-one distributed states/parameters for these. Retain them in `constants.py` for provenance; do not invent surrogate CINDER parameters or substitute the local node threshold for CINDER's gross contact switching. Figures 41/45 use the *undamped* branch.

The inability to reproduce Ballew's exact zero-tension internal nodal state is a structural initialization difference and should be discussed with the eventual results rather than hidden by tuning.

## A9 — Meaning of `Transmission Ratio = 8.93`

**Source:** Table A1 reports `Transmission Ratio = 8.93` beside the ATV/tire data without a more specific label.

**CINDER:** interpret it as the fixed reduction between CVT output and wheel for vehicle kinematics, road-load torque and inertia reflection.

**Why this matters:** Ballew's output load is not a prescribed brake torque; it is generated by the simulated vehicle through this downstream mapping. An incorrect interpretation of `8.93` changes both reflected inertia and road-load torque.

**Status:** keep the interpretation explicit until confirmed from Ballew's vehicle equations/implementation or another source.
