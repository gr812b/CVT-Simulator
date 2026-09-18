# CINDER Results Working Ledger

**Status:** active / late-stage pre-writing  
**Updated:** 2026-09-15  
**Rule:** Record the scientific question first. Promote a conclusion only after a reproducible study supports it. Nothing here is a frozen manuscript claim unless explicitly marked as such.

## 1. Current position

The results programme is no longer primarily building verification infrastructure. The major verification studies now exist, the Ballew comparison is established, and the actuator-dynamics family has matured into a complete scientific result. The remaining work is a short set of pre-writing studies followed by a deliberate synthesis pass.

The current boundary is:

1. finish the final closure-conditioning question;
2. freeze the slotted helix as the canonical results topology across maintained studies;
3. analyze the retained reduced-belt transient terms and coherent reductions;
4. turn the existing launch/hill case into a mechanism-resolved causal study;
5. compare bilateral/slotted and unilateral helix behavior under load reversal and reverse power flow;
6. stop adding studies, clean the result tree, decide the Chapter 4 story, and write.

Do not create another major study after these unless one of them exposes a genuine missing scientific requirement.

## 2. Results-program status

| Item | Status | Next action |
|---|---|---|
| Results baseline | **DONE / FROZEN** | CINDER `v1.1.2` remains the mechanics release for this results programme. |
| Release-scoped results tree | **DONE / FROZEN** | Continue under `results/cinder-v1.1.2/`; never overwrite prior-release provenance. |
| General results helix topology | **POLICY DECLARED / AUDIT TO FREEZE** | Verify that every maintained general-purpose study uses the zero-clearance bilateral/slotted results decoder and records that topology in its provenance. |
| Mechanical-energy consistency | **DONE / PASS** | Preserve as release-level energetic verification. |
| Mechanical invariants / capability | **DONE / PASS** | Preserve broad operating-domain evidence and capability interpretation. |
| Solver convergence | **DONE** | Preserve the formal sweep and publication-facing figures; dense overnight work remains exploratory only. |
| Ballew model-to-model comparison | **DONE / INTERPRETATION RECORDED** | Use during Chapter 4 synthesis; never present as direct experimental validation. |
| Actuator dynamics / coupling | **DONE / MATURE RESULT FAMILY** | Use baseline ablation, coupling decomposition, validity envelopes, controlled transients, and commercial-scale sensitivity during synthesis. |
| Closure conditioning | **FINALIZATION** | Complete the true one-free-lambda mixed-contact root study, then freeze the closure result. |
| Reduced-belt transient mechanics | **NEXT MAJOR STUDY** | Inventory retained terms, measure them, then build only coherent reductions supported by the inventory. |
| Launch / hill mechanism study | **INFRASTRUCTURE EXISTS / SCIENTIFIC NARRATIVE PENDING** | Convert the existing launch-hill case into a causal mechanism-resolved result. |
| Slotted vs unilateral helix | **NEW FINAL PRE-WRITING STUDY** | Compare performance and topology under sudden wheel load and reverse-power-flow cases using a mechanically explicit unilateral loss-of-contact idealization. |
| Chapter 4 structure / story | **HOLD** | Decide only after the five pre-writing tasks above are complete. |

## 3. Frozen baseline and canonical results topology

### 3.1 Release baseline

The current results workspace is tied to:

```text
CINDER source tag: cinder-v1.1.2
tag commit:        7637a38b4fb9ec21dfb953c1c80a27ec5f389654
PyPI package:      cinder-cvt==1.1.2
```

Every paper-facing result must remain traceable to the installed release wheel and a fully resolved input/provenance artifact.

### 3.2 Canonical helix policy

The standard results model is a **zero-clearance bilateral/slotted secondary helix**. The production signed helix torque/force law, torsional spring, movable-member inertia, and shaft-reaction equations remain unchanged. The results-local change removes only the selected-unilateral-flank compression inequality: when the required signed reaction changes sign, the opposite slot flank carries it.

This topology is the default because the general results programme is intended to interrogate belt, closure, actuator, hybrid, and system dynamics without terminating a trajectory merely because one specific unilateral helix flank would lift off.

The dedicated **slotted-versus-unilateral helix study is the intentional exception**. It should use both topologies because helix contact loss is the scientific question.

### 3.3 Audit required before the next result families are frozen

Check every maintained study and helper for the following:

- general-purpose studies decode through the shared results-reference model;
- the resolved provenance records the bilateral/slotted topology;
- no general-purpose study accidentally calls the published unilateral decoder directly;
- old artifacts generated with a different topology are not silently reused;
- any affected study is regenerated before final paper figures are selected;
- the dedicated helix-topology comparison clearly declares when it switches back to a unilateral model.

Once this audit passes, treat the reference topology as frozen for the remainder of the results campaign.

## 4. Completed verification and comparison foundation

### 4.1 Mechanical-energy consistency — DONE

Question: **Does modeled external work equal retained stored-energy change plus explicitly modeled irreversible losses, up to numerical error?**

Current conclusion:

- the material structural energy inconsistency found during development was corrected before `v1.1.2`;
- exact event/capture energy accounting closes to numerical precision;
- the remaining continuous residual is numerical-error scale relative to total energy throughput;
- refinement changes the small residual without changing the physical trajectory.

Interpretation boundary: this verifies the retained equations and event bookkeeping. It does not establish that omitted physical losses or compliance are negligible in real hardware.

### 4.2 Mechanical invariants / operating-domain capability — DONE

Question: **Do accepted CINDER states and hybrid successors satisfy the equations, constraints, and topology/admissibility conditions of the retained model?**

The current operating-domain audit goes well beyond one nominal launch. It challenges static rest; deadzone and engaged structural states; forward and reverse rotation; both shift directions; both signed single-interface slip directions; all four both-slip quadrants; geometry-domain closure; belt tension and distributed normal loading; stop/mechanism reactions; 8x8 closure self-consistency; and exact hybrid successor states.

The rare-contact reproduction anchors remain valid only if the production classifier, exact invariants, continuation, and successor checks all pass. They are not bypasses.

Interpretation boundary: this is broad operating-domain evidence, not a mathematical proof over every real-valued initial condition.

### 4.3 Solver convergence — DONE

Question: **Are the reported hybrid trajectories properties of the equations rather than artifacts of LSODA tolerances or maximum step size?**

The formal study now includes the full paper-facing `rtol x max_step` sweep, an independent absolute-tolerance sweep, all five state trajectories, normalized RMS / maximum / final-state errors, transition counts and exact signatures, event-time errors, regime-history mismatch, integration cost metrics, and publication-facing heatmaps, cost curves, sensitivity plots, and trajectory overlays.

The optional dense overnight explorer remains explicitly supplementary and must not replace the frozen formal dataset.

### 4.4 Ballew 2015 comparison — DONE

Question: **Does an independently architected transient rubber-belt model produce comparable macroscopic behavior under matched protocols?**

Retain both protocols:

1. **force replay** — impose the digitized Ballew primary axial-force history and compare plant response;
2. **reconstructed closed loop** — reconstruct the published control law around unchanged CINDER and compare controlled outputs.

Interpretation boundary: this is a **model-to-model comparison**, not direct experimental validation of CINDER. Controlled-output agreement does not imply identical internal plant mechanics; force replay is the cleaner plant-mapping comparison.

### 4.5 Actuator dynamics / axial-rotational coupling — DONE

Question: **What changes when the primary flyweight and secondary helix mechanisms are treated dynamically instead of quasi-statically, and at what physical scales do those corrections matter?**

The mature family contains the four-model Baja baseline ablation, same-state component corrections, coupling-energy/generalized-inertia decomposition, equation-derived quasi-static validity envelopes, controlled target-level transients, source-registered commercial-scale sensitivity, and a commercial-secondary mechanism-transplant trajectory demonstration.

The retained interpretation remains scale-aware: a small Baja-baseline correction can justify a quasi-static approximation at that scale, while larger commercial-scale corrections show that the retained dynamic terms are not intrinsically negligible.

## 5. Closure conditioning — final task before freezing verification

### 5.1 Question

**How well posed is the instantaneous closure, locally and globally, and does root multiplicity require two simultaneously free sticking tractions?**

Keep three objects distinct:

1. the 8x8 mechanical closure for a specified traction pair;
2. the 2x2 stick-stick residual map in `(lambda_p, lambda_s)`;
3. the 1D mixed-contact residual when one interface slides and its kinetic lambda is fixed while the other interface sticks.

### 5.2 Current established picture

For a specified traction pair, the production 8x8 mechanical system has one solution whenever the assembled matrix is nonsingular. Finite-lambda conditioning walls arise from the coupled assembled equations rather than from a simple pole in an isolated wrap function.

The stick-stick work has also shown a useful distinction between local and global behavior:

- physically encountered roots are generally locally regular and well conditioned;
- severe 8x8 conditioning ridges often lie in mechanically/topologically inadmissible regions;
- the broader stick-stick residual map can contain multiple roots;
- continuation/manifold work indicates that these are structured branches of a folded nonlinear solution manifold rather than random optimizer artifacts;
- alternate arms can approach friction, belt-contact, or mechanism-admissibility limits.

These are results of the retained one-gross-traction-state-per-wrap model. They must not be promoted as proof that a spatially resolved real belt contact possesses multiple interchangeable physical states.

### 5.3 Final missing question: true mixed-contact 1D closures

Study both branches:

- **primary sliding / secondary sticking**;
- **primary sticking / secondary sliding**.

For the sliding contact, kinetic traction is fixed by the active slip direction. The sticking contact retains one unknown static traction utilization. The closure problem is therefore one-dimensional.

Determine whether the 1D residual can have more than one admissible root at one frozen mechanical state; whether any multiple roots lie on a connected folded branch or are separated by inadmissible intervals; whether ordinary physical trajectories ever approach a 1D fold or root ambiguity; and whether root multiplicity appears to be fundamentally associated with the two-free-lambda stick-stick closure.

Record at minimum the scalar residual over the admissible traction interval, all sign-changing or tangent roots found robustly, the local derivative at each root, mechanical/topological admissibility margins, and continuation with a meaningful control parameter if multiplicity is discovered.

### 5.4 Exit criterion

Closure conditioning is **DONE** when both mixed branches have been searched broadly enough to answer the multiplicity question and the result is summarized beside the existing 8x8 and stick-stick findings. Do not expand the closure study further unless the 1D search reveals a new unresolved mechanism.

## 6. Reduced-belt transient mechanics — next major scientific study

### 6.1 Positioning

CINDER does not claim that one inextensible belt transport coordinate and one gross traction state per wrap are the final representation of a rubber V-belt. The value of the current formulation is that it closes that reduced whole-belt problem dynamically, allowing the transient terms retained by the reduction to be isolated and tested.

The study should therefore answer:

**Which transient terms retained by CINDER materially affect the reduced whole-belt dynamics, when do they matter, and which coherent simplifications are actually justified?**

### 6.2 Stage 1 — exact term inventory

Identify every retained transient/inertial contribution in pulley-wrap radial balance, pulley-wrap tangential balance, wrap tension evolution, straight-span balances, moving span-boundary momentum transport, whole-belt transport equation, and closed-loop tension compatibility. Tie each term explicitly to the derivation and to its physical acceleration, momentum, or moving-boundary origin.

### 6.3 Stage 2 — magnitude and regime audit

For each term, record its signed time history; normalize it against the appropriate local force, tension, acceleration, or power scale; inspect ordinary launch, active shift, a strong backshift/load transient, and a relevant contact transition if one excites the term.

The purpose is not to rank terms by arbitrary raw magnitude, but to identify the regimes in which a classical reduction does or does not remain accurate.

### 6.4 Stage 3 — coherent reductions

Only after the inventory and magnitude audit:

- remove one physically coherent class of terms at a time;
- preserve the rest of the mechanical structure consistently;
- rerun energy/invariant checks where appropriate;
- compare complete trajectories against the full reduced-belt formulation.

Possible useful outcomes are all scientifically valid: a term is negligible in ordinary operation, justifying a simpler model; a term matters only during engagement or rapid shifting, defining the limit of a quasi-static reduction; or a term materially changes ordinary trajectories, identifying mechanics that reduced models should retain.

### 6.5 Claim boundary and future work

Do not frame these terms as the final word in belt physics. The natural next model class resolves more of the spatial belt/contact field, for example longitudinal strain transport, local traction state, local belt velocity, and solution-dependent contact extent. The present study establishes what happens **inside the dynamically closed reduced representation** and helps identify where that representation becomes strained.

## 7. Mechanism-resolved launch / hill study

### 7.1 Question

**How does an external load disturbance propagate through the mechanically actuated CVT, from road load to internal reactions to ratio and vehicle response?**

The existing launch-hill runner already provides the baseline infrastructure. The remaining work is not to create a tuning contest; it is to choose a clean case and expose the causal chain.

### 7.2 Desired narrative

```text
road / wheel load change
-> secondary shaft demand
-> helix + belt + spring axial balance
-> normal loads and traction utilization
-> movable-sheave acceleration
-> ratio change / backshift
-> shaft-speed and vehicle response
```

Where useful, include the primary actuator response in the same causal chain rather than treating either pulley in isolation.

### 7.3 Preferred outputs

Prioritize road grade / external load; primary and secondary speeds plus vehicle speed; shift coordinate and effective ratio; movable-sheave axial-force contributions; pulley normal resultants; traction utilizations and relative contact speeds; transmitted torques; and the relevant contact/structural regime.

Use the canonical slotted results topology unless the purpose of a run is explicitly the helix-topology comparison in the next section.

## 8. Slotted versus unilateral helix — final dedicated design study

### 8.1 Strong scientific/design question

**Does a zero-clearance bilateral/slotted helix materially change or improve transient CVT behavior when the demanded helix reaction reverses sign, compared with a conventional single selected flank that can lose contact?**

This study is deliberately different from the general results policy. It exists because CINDER solves the movable secondary member as a free body and can therefore determine the contact reaction required to enforce the helix kinematics, including whether the selected unilateral flank would need to pull.

### 8.2 Models to compare

#### A. Bilateral/slotted reference

The signed helix reaction is supported in either direction. When the required reaction changes sign, the opposite slot flank carries it with zero clearance. The helix kinematic coupling remains active.

#### B. Ideal unilateral selected-flank model

While the selected flank is engaged, require a compressive reaction.

When the demanded reaction reaches zero and would reverse sign:

- declare helix contact loss;
- set helix contact reaction to zero;
- release the corresponding helix contact constraint so the movable member is not artificially forced to follow an engaged helix kinematic relation without a supporting reaction.

For the first-order design comparison, this detached mode may intentionally omit backlash traversal, impact loss, flank friction, and detailed opposite-flank capture. State this clearly. Those effects belong to a higher-fidelity hardware-specific contact model.

A simple force-clipping model that keeps the helix kinematic constraint active while setting only the axial force to zero may be retained as a sensitivity check, but it should not be the primary physical comparison.

### 8.3 Cases

At minimum use:

1. an ordinary forward-drive reference, to establish whether the topologies are effectively identical when the selected flank remains loaded;
2. a sudden large wheel/secondary load increase chosen to challenge the reaction sign;
3. a reverse-power-flow case, such as engine braking or imposed negative secondary torque, where opposite-flank demand is expected to be especially informative.

Do not optimize the disturbance solely to maximize the difference. Choose mechanically interpretable load levels and report why each case was selected.

### 8.4 Quantities to compare

Track the signed helix reaction, helix contact state, secondary movable-sheave position/speed/acceleration, belt and spring axial contributions, secondary normal resultant, shaft torque and speed, CVT ratio, vehicle response where applicable, and traction utilization/contact regime.

Useful bilateral-demand diagnostics include

\[
D_- = \frac{\text{time requiring opposite-flank reaction}}{\text{total case time}},
\]

and

\[
I_- = \int_{F_{\rm helix}<0}|F_{\rm helix}|\,dt,
\]

with sign convention stated explicitly.

### 8.5 Interpretation boundary

Do not prejudge that the slotted design is universally better. Plausible outcomes include bidirectional support preserving intended torque-to-axial coupling and improving transient control; bidirectional support creating stronger axial response during reverse power flow while unilateral lift-off naturally decouples it; or both designs being effectively identical in normal forward drive and differing only in severe/reversed transients.

The study may support a claim that CINDER can test unilateral helix-contact admissibility and quantify its system consequence. A stronger priority/first-in-literature claim must wait for the final literature comparison.

## 9. Results synthesis gate

Only after Sections 5-8 above are complete should the project step back and decide the manuscript structure.

At that point assemble energy consistency, mechanical invariants/capability, solver convergence, closure conditioning, Ballew comparison, actuator dynamics, retained-belt mechanics, the mechanism-resolved launch/hill result, and the slotted-versus-unilateral helix result side by side.

Then decide which are headline scientific results; which are supporting verification; which plots belong in the main paper; which diagnostics belong in appendices or repository artifacts; which studies can be combined into one subsection without losing their distinct questions; and what order best teaches the machine rather than reproducing the chronological research process.

A likely high-level logic remains:

```text
credibility of the solved model
-> comparison with established work
-> consequences of the retained dynamic mechanics
-> mechanism-resolved system behavior and design insight
```

This is deliberately **not frozen** until the remaining studies are complete.

## 10. Interpretation boundaries to preserve

- Energy, invariants, closure conditioning, and solver convergence are **verification**, not physical validation.
- Ballew is a **model-to-model comparison**, not direct CINDER experimental validation.
- A mathematically admissible root of the reduced contact closure is not automatically evidence of multiple physical real-belt states.
- Severe conditioning or topology failure can reveal the limit of the retained reduction rather than impossible real-world mechanics.
- A small dynamic term can still justify a useful reduction; novelty does not require a large effect.
- The canonical slotted helix is a deliberate results topology, not a claim that every real CVT should use a slot.
- The slotted-versus-unilateral study must distinguish zero-clearance bilateral support from real backlash, free flight, impact, and friction.
- Retained belt terms are claims about the current reduced whole-belt representation unless literature and evidence support a broader statement.
- Strong novelty wording should be frozen only after the final literature matrix is updated.

## 11. Future-work posture

Do not apologize for the present reductions. The paper's contribution is to make the chosen reduced CVT model dynamically complete enough that its mechanisms, numerical structure, and limits can be interrogated directly.

The natural next generation should spend additional model complexity on spatial resolution, especially longitudinal belt deformation / strain transport; local rather than one-per-wrap traction state; spatially varying belt/contact velocity; local stick/slip zones; solution-dependent contact extent / lift-off; and hardware-specific helix clearance, opposite-flank capture, and impact where needed.

The present results should therefore be posed as:

1. what is established within the current reduced model;
2. what mechanism or limitation that teaches;
3. what a more spatially resolved future model may alter or resolve.

## 12. Immediate execution order

1. **Closure:** finish the primary-slip/secondary-stick and primary-stick/secondary-slip 1D root study.
2. **Reference topology:** audit and freeze the bilateral/slotted decoder across all maintained general results.
3. **Reduced belt:** perform the exact term inventory, magnitude audit, and coherent reductions.
4. **Mechanism transient:** refine the launch/hill case into the causal paper-facing example.
5. **Helix design:** run the dedicated bilateral/slotted versus unilateral loss-of-contact study under ordinary, sudden-load, and reverse-power-flow cases.
6. **Synthesis:** clean artifacts, update the literature/claim matrix, decide the final Chapter 4 spine, and only then draft the results section.
