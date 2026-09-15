# CINDER 1.1.2 — Helix Contact-Topology Study

**Status:** exploratory / mechanism-discovery phase. This directory is not yet a final-results study.

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

The full matrix uses secondary drive torques of +120, +300, and +600 N·m, primary targets of -5 and -25 N·m, and restarts at mid ratio, high ratio, and a specially chosen high-dynamic natural state.

#### D. Bench resisting load

Again remove the vehicle road-load boundary, but apply direct resisting secondary torques of -120, -300, and -600 N·m. Run these at low, mid, and high ratio plus the high-dynamic restart.

This complements E3 by changing the boundary condition itself rather than simply adding a torque on top of the vehicle model.

#### High-dynamic restart

In addition to the ratio-based restart states, E4 scans the natural conditioning run and selects the engaged state maximizing

\[
|M_{h,\alpha_s}| + |M_{h,\ddot s}| + |M_{h,\dot s^2}|.
\]

That deliberately gives the shaft-acceleration, shift-acceleration, and helix-curvature terms a chance to control the sign reversal. Otherwise the study could accidentally reduce to the trivial observation that a sufficiently large reversed belt torque makes `M_h` negative.

For every completed E4 case, the artifact set records the minimum-margin decomposition, the dominant negative contribution at that instant, the complete raw trace, contact/traction state, shift response, normal force, hybrid transitions, and the opposite-flank duration/impulses.

### E5 — candidate reruns after interpretation

E5 is intentionally **not** hard-coded yet. After the E1–E4 artifact ZIP is inspected, choose a small physically diverse set of cases and rerun them with tighter tolerances, denser sampling, and any scenario refinement suggested by the discovery results.

### E6 — physical selected-flank comparator

Only after useful lift-off candidates are established should the ideal unilateral detached topology be added. When `M_h` reaches zero and would become tensile, the selected flank must release and the helix kinematic constraint must release with it. The movable member's relative rotation then becomes an independent motion until a re-contact rule is introduced.

A `max(0, F_h)` model that leaves `\theta=\theta(s)` constrained may be retained only as an explicitly labelled sensitivity check.

### E7 — topology consequence

Use the E5 representative cases to compare the slotted trajectory with true selected-flank detachment. Only at that point do trajectory/performance differences become study results.

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
6. writes provenance and raw/summary artifacts; and
7. creates
   `results/cinder-v1.1.2/studies/helix-topology/helix_topology_discovery_artifacts.zip`.

**Send that ZIP back for interpretation.** It is the intended handoff between exploration and E5 candidate selection.

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
- `artifacts/provenance/` — study configuration and pinned upstream manifest;
- `artifacts/RUN_COMPLETE.json` — run mode and completion marker.

The shortlists are **discovery aids, not rankings of CVT performance**. Failed cases remain in the summaries with their failure reason so the exploration does not silently discard difficult regimes.

## Interpretation boundary

No conclusion in E1–E4 should assume that the slotted topology is inherently better. A negative selected-flank margin in the slotted model means that the constrained slotted solution requires opposite-flank support. It does **not** yet show what a real one-flank mechanism would do after separation.

Real backlash, free flight, impact, friction, and finite opposite-flank capture dynamics also remain outside the zero-clearance slotted idealization and the first detached comparator.
