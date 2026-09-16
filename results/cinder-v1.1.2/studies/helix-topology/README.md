# CINDER 1.1.2 — Helix Contact-Topology Study

**Status:** exploratory / targeted lift-off-envelope refinement. This directory is not yet a final-results study.

## Scientific question

When the secondary helix reaction changes sign, when does the assumed helix contact topology matter to the CVT response?

The shared CINDER results reference model is the **zero-clearance bilateral/slotted secondary helix** defined in `../../defaults/reference_model/slotted_helix.py`. It keeps the production signed helix equations unchanged and permits either reaction sign; a sign reversal is interpreted as transfer to the opposite slot flank. The released one-flank model remains useful as a contact-admissibility reference, but a physically meaningful one-flank comparison must release the helix kinematic constraint when contact is lost. Simply clipping the helix force to zero while retaining the constraint is not the primary comparator.

This study therefore starts by discovering **where and why** sign reversal occurs before asking whether it improves or degrades any vehicle-level metric.

## Contact quantity

For the production dynamic helix, define the signed reacted torque on the selected flank

\[
M_h = f\,\tau_s + k_\theta(\theta_{\rm pre}-\theta)
      - I_M\left(\alpha_s+\ddot\theta\right),
\]

with

\[
\ddot\theta = \theta'(s)\,\ddot s + \theta''(s)\,\dot s^2,
\qquad
F_h = M_h\,\frac{d\theta}{dx_s}.
\]

`M_h` is the primary contact-topology diagnostic. Under the released selected-flank convention, `M_h > 0` is compressive support on the selected flank, `M_h = 0` is the lift-off boundary, and `M_h < 0` means the same constrained motion would require the opposite flank. In the slotted reference model, negative `M_h` is not an invalid state; it means the opposite slot flank is carrying the reaction.

The axial force `F_h` is still recorded because it enters the secondary axial balance, but its sign is not used by itself to decide flank admissibility when the helix motion ratio varies.

## Causal order of the study

The working causal chain is

**reaction demand → flank admissibility → contact topology → secondary force balance → shift/contact response → vehicle consequence**.

The exploratory runner intentionally stops before the topology-comparison step. Its job is to find useful states and explain the reaction demand that gets us there.

## Exploration stages

### E0 — formulation and sign audit

Freeze the exact production helix equation, coordinate signs, and results-local slotted policy. Confirm that all reported quantities use one convention and that the slotted helper changes topology only, not the signed constitutive law.

**Gate:** no unexplained sign conversions; `M_h` reconstructed from reported terms agrees with the production relation.

### E1 — frozen reaction boundary map

At engaged shift positions spanning the operating range, set the dynamic accelerations to zero and map

\[
M_{h,\mathrm{qs}}(s,\tau_s)
 = f\tau_s+k_\theta[\theta_{\rm pre}-\theta(s)].
\]

The zero contour gives the torque required to transfer support from the selected flank to the opposite slot flank. This is a geometry/spring map, not a vehicle simulation.

### E2 — natural forward-operation control

Run the ordinary flat full-throttle Baja reference case with the slotted reference topology and record the complete signed helix decomposition.

This establishes whether normal forward operation stays comfortably on one flank and provides the natural trajectory used to obtain physically reached restart states.

### E3 — controlled secondary-torque screen

Restart from naturally reached low-, mid-, and high-shift states and apply smooth signed secondary-shaft torque perturbations with multiple ramp times.

This is the cleanest way to answer the first mechanics question: **how much secondary torque does it take to approach or cross `M_h = 0` at different ratios?** The screen deliberately includes aggressive values because it is a mechanism experiment, not yet a vehicle realism claim.

Cases are classified as:

- **one-flank:** selected-flank margin stays positive;
- **near boundary:** the minimum absolute margin approaches zero without sustained reversal;
- **opposite-flank required:** the slotted solution spends nonzero time at `M_h < 0`.

### E4 — broad scenario discovery

E4 expands the search so a zero crossing is not discovered only by directly forcing secondary torque. It uses four distinct physical families.

#### A. Hill / load entry

Start from naturally reached mid- and high-ratio states with the ordinary full-throttle Baja engine and vehicle boundary, then ramp from flat road to increasingly severe uphill grades. The full matrix includes 15°, 30°, and deliberately aggressive 45° targets with both fast and slower transitions.

This family asks whether a genuine road-load transient can create or deepen opposite-flank demand.

#### B. Downhill + engine braking / reverse-power-flow forcing

Start from mid- and high-ratio states. At the same time that the route moves toward level/downhill grades, smoothly replace the full-throttle primary torque with a prescribed resisting torque. The matrix includes level, -15°, -30°, and -45° grades together with -5, -20, and -40 N·m primary targets.

The large values are deliberate exploration points. This family is meant to expose reverse-power-flow and engine-braking-like mechanics, not to claim every combination is a realistic Baja operating point.

#### C. Bench secondary back-drive

Remove the vehicle road-load boundary and replace the secondary with a prescribed shaft-torque boundary. Drive the secondary positively while the primary transitions to a resisting torque. This creates a controlled back-drive experiment without road-load dynamics obscuring the mechanism.

The full matrix uses secondary drive torques of +20, +60, and +120 N·m, primary targets of -5 and -25 N·m, a 0.3 kg·m² bench-side inertia, and restarts at mid ratio, high ratio, and a specially chosen high-dynamic natural state.

#### D. Bench resisting load

Again remove the vehicle road-load boundary, but apply direct resisting secondary torques of -20, -60, and -120 N·m with the same 0.3 kg·m² bench-side inertia. Run these at low, mid, and high ratio plus the high-dynamic restart.

This complements E3 by changing the boundary condition itself rather than simply adding a torque on top of the vehicle model.

#### High-dynamic restart

In addition to the ratio-based restart states, E4 scans the natural conditioning run and selects the engaged state maximizing

\[
|M_{h,\alpha_s}| + |M_{h,\ddot s}| + |M_{h,\dot s^2}|.
\]

That deliberately gives the shaft-acceleration, shift-acceleration, and helix-curvature terms a chance to control the sign reversal. Otherwise the study could accidentally reduce to the trivial observation that a sufficiently large reversed belt torque makes `M_h` negative.

For every completed E4 case, the artifact set records the minimum-margin decomposition, the dominant negative contribution at that instant, the complete raw trace, contact/traction state, shift response, normal force, hybrid transitions, and the opposite-flank duration/impulses.

### E5 — lift-off envelope and dynamic-novelty refinement

E5 is now implemented from the E4 discoveries. It stops broad exploration and maps the selected-flank boundary around the physically informative cases.

#### A. Vehicle braking / downhill envelope

Use naturally reached 30%, 50%, and 70% shift states. At each state, sweep level and downhill grades of 0°, -15°, -30°, and -45° while the primary boundary transitions from the full-throttle engine to prescribed braking torques from -5 through -48 N·m. The coarse grid includes -28 N·m because that is the largest braking-torque magnitude configured anywhere in the pinned reference engine boundary. Values beyond that are explicitly labelled **extension cases**, not validated engine-braking operating points.

Whenever adjacent coarse cases bracket `M_h=0`, locally bisect the bracket with tighter solver settings. The threshold table therefore estimates the braking magnitude at lift-off versus ratio and grade rather than reporting only isolated examples.

#### B. Full-dynamic versus quasi-static admissibility

For every E5 trace also reconstruct

\[
M_{h,\mathrm{QS}} = f\tau_s+k_\theta(\theta_{\rm pre}-\theta),
\]

and

\[
M_{h,\mathrm{dyn}} = -I_M\alpha_s-I_M\theta'(s)\ddot s-I_M\theta''(s)\dot s^2.
\]

A **strict dynamic-only lift-off** is a case in which the full margin becomes negative while the minimum trajectory-frozen quasi-static margin remains positive over the resolved post-onset interval. E5 also records the duration for which `M_h<0` and `M_{h,QS}>0`, and the value of `M_{h,QS}` at the linearly interpolated first full-dynamic zero crossing.

Near the coarse vehicle boundary, rerun the same torque/grade condition with 20, 50, 100, 250, and 500 ms ramps. This deliberately searches for a clean vehicle case where the inertial helix terms create lift-off before belt slip or a travel-stop impact.

#### C. Bench dynamic-only refinement

Refine the E4 inertia-dominated back-drive discovery around the naturally reached high-dynamic restart using moderate secondary drive torques and a 0.3 kg·m² bench-side inertia. This family is a mechanism-isolation experiment: its purpose is to find the cleanest state for which the full dynamic helix is inadmissible while the torque+spring diagnostic remains admissible.

E5 is still a **topology-discovery/refinement** stage. A dynamic-only event establishes that retaining movable-member inertia changes flank admissibility on the same trajectory. It does not, by itself, establish a literature-priority claim that no previous dynamic helix model could predict the effect.

### E5.5 — forward-power dynamic-only lift-off isolation

E5.5 is a mechanism-isolation study aimed at the stronger condition

\[
P_{\mathrm{belt},s}>0,\qquad
\text{stick--stick},\qquad
M_{h,\mathrm{QS}}>0,\qquad
M_h<0.
\]

The secondary torsional preload is swept through 300°, 270°, 240°, 210°, and 180°.  Each preload is rebuilt into the actual assembly and **reconditioned from launch** before 30%, 50%, and 70% shift restart states are selected.  This prevents preload from being treated as a fake algebraic offset: any accompanying changes in clamp force, belt traction, engagement history, and shift trajectory are retained.

Two target perturbation families deliberately seek rapid backshift while preserving forward power: a smooth throttle/drive-torque drop and a sudden increase in resisting secondary load.  Opposite-sign torque-rise and secondary-assist cases are retained as sign controls.  A 50 ms coarse screen is followed only where useful by 5, 10, 25, 50, 100, and 250 ms ramp-rate refinement.

A **gold case** requires the first full-dynamic zero crossing to occur with positive trajectory-frozen `M_h,QS`, positive secondary internal belt power, stick--stick belt contact inside a friction guard, no hybrid transition after perturbation onset before the crossing, and more than 2% of shift travel to either stop.  In addition, `M_h,QS` must remain positive over the complete resolved post-onset trajectory.  This deliberately excludes reverse-power, belt-slip, and travel-impact explanations for the flank change.

E5.5 also records the individual shaft-acceleration, shift-acceleration, and profile-curvature contributions at the first crossing so the study can distinguish a wheel/shaft-acceleration mechanism from the much larger `-I_M theta'(s) s_ddot` rapid-shift mechanism.

### E6 — physical selected-flank comparator

Only after useful lift-off candidates are established should the ideal unilateral detached topology be added. When `M_h` reaches zero and would become tensile, the selected flank must release and the helix kinematic constraint must release with it. The movable member's relative rotation then becomes an independent motion until a re-contact rule is introduced.

A `max(0, F_h)` model that leaves `\theta=\theta(s)` constrained may be retained only as an explicitly labelled sensitivity check.

### E7 — topology consequence

Use the E5/E5.5 representative cases to compare the slotted trajectory with true selected-flank detachment. Only at that point do trajectory/performance differences become study results.

## Primary discovery metrics

For a case of duration `T`, using the selected-flank sign convention above:

- `D_opp_case = measure(M_h < 0) / T` — fraction of total case time for which the slotted solution requires the opposite flank;
- `D_opp_engaged` — the same fraction restricted to resolved engaged samples;
- `I_opp_tau = ∫_{M_h<0} |M_h| dt` — opposite-flank reacted-torque impulse;
- `I_opp_force = ∫_{M_h<0} |F_h| dt` — corresponding axial-force impulse;
- minimum signed margin and minimum absolute margin;
- number and timing of zero crossings;
- complete belt / torsional-spring / shaft-acceleration / shift-acceleration / curvature decomposition at the minimum margin;
- shift excursion, speed, acceleration, normal resultant, belt traction utilization, and hybrid transitions around the crossing.

The torque-domain metrics are primary because `M_h` is the unilateral-contact margin exposed by the production helix law. Force-domain metrics are retained to connect the topology event to the axial sheave balance.

## One-command workflow

From the repository root, after the release-scoped results environment is installed, the **full discovery run** is simply:

```bash
python results/cinder-v1.1.2/studies/helix-topology/run.py
```

That command:

1. verifies `cinder-cvt==1.1.2` and the pinned release tag;
2. runs E1 reaction mapping;
3. runs E2 natural forward control;
4. runs the complete E3 controlled torque screen;
5. runs the complete E4 multi-family scenario discovery;
6. runs E5 lift-off-envelope and dynamic-novelty refinement;
7. runs E5.5 preload/transient dynamic-only isolation;
7. writes provenance and raw/summary artifacts; and
8. creates
   `results/cinder-v1.1.2/studies/helix-topology/helix_topology_discovery_artifacts.zip`.

**Send that ZIP back for interpretation.** It is the intended handoff between lift-off-envelope refinement and the E6 detached selected-flank derivation/comparison.

A smoke test is available with:

```bash
python results/cinder-v1.1.2/studies/helix-topology/run.py --quick
```

Quick mode is only for checking that the installation and scenario plumbing work. Do not use the quick ZIP for scientific interpretation.

The standalone verifier remains available as:

```bash
python results/cinder-v1.1.2/studies/helix-topology/verify_study.py
```

## Artifact layout

The full runner writes:

- `artifacts/reaction-map/` — frozen `M_h=0` map;
- `artifacts/forward-control/` — ordinary flat full-throttle trajectory;
- `artifacts/stress-screen/` — E3 controlled secondary-torque matrix and shortlist;
- `artifacts/scenario-discovery/` — E4 hill, downhill/engine-braking, bench-backdrive, and bench-load matrix, full trace, restart states, and shortlist;
- `artifacts/liftoff-envelope/` — E5 vehicle threshold map, full-vs-QS diagnostics, dynamic-ramp refinement, bench dynamic-only refinement, and candidate catalogue;
- `artifacts/dynamic-only-liftoff/` — E5.5 preload conditioning, transient/ramp-rate sweep, first-crossing audit, retained traces, and gold-candidate catalogue;
- `artifacts/provenance/` — study configuration and pinned upstream manifest;
- `artifacts/RUN_COMPLETE.json` — run mode and completion marker.

The shortlists are **discovery aids, not rankings of CVT performance**. Failed cases remain in the summaries with their failure reason so the exploration does not silently discard difficult regimes.

## Interpretation boundary

No conclusion in E1–E5.5 should assume that the slotted topology is inherently better. A negative selected-flank margin in the slotted model means that the constrained slotted solution requires opposite-flank support. It does **not** yet show what a real one-flank mechanism would do after separation.

Real backlash, free flight, impact, friction, and finite opposite-flank capture dynamics also remain outside the zero-clearance slotted idealization and the first detached comparator.
