# CINDER Results Programme — Context Snapshot

**Status date:** 2026-09-15  
**Purpose:** Preserve the state of the CINDER `v1.1.2` results programme immediately before the final pre-writing studies. This file is a historical snapshot. Do not continuously edit it after the programme moves forward; update the working ledger instead and create a later snapshot when another natural milestone is reached.

## 1. Executive state

The project has moved substantially beyond the 2026-09-09 planning snapshot.

CINDER `v1.1.2` is now the frozen release used by the results tree. Mechanical-energy consistency, broad mechanical-invariant/capability testing, solver convergence, the Ballew comparison, and the actuator-dynamics family have all progressed from plans into maintained result studies.

Closure conditioning is the only remaining verification question still actively being closed. The broad stick-stick investigation has gone beyond local condition numbers into global residual geometry, root census, continuation, and folded solution-manifold structure. One final question remains: whether analogous multiplicity can occur in the true one-dimensional mixed stick/slip closures.

After that, the remaining work is scientific rather than infrastructural:

- audit and freeze the bilateral/slotted helix as the default results topology;
- analyze retained transient terms in the reduced whole-belt model;
- turn the launch/hill case into a mechanism-resolved explanatory result;
- compare bilateral/slotted versus unilateral helix behavior under large load and reverse-power-flow transients;
- then stop adding studies and design the final Chapter 4 story.

This is therefore the transition from **results construction** to **results synthesis**.

## 2. Repository / release state at snapshot

Current results pull request:

```text
Repository: gr812b/CVT-Simulator
PR:         #487 — Cinder-v1.1.2 Complete Results
State:      open / draft
Head:       results
Base:       develop
Head SHA:   2c26740dc78e97e107e61fedaeae3a2c859d7bc4
```

At the time of this snapshot the GitHub metadata reported 23 commits, 155 changed files, and the PR as not currently mergeable. Treat mergeability as transient repository state rather than a scientific issue; branch synchronization/conflict cleanup belongs near final consolidation.

Frozen results release:

```text
CINDER source tag: cinder-v1.1.2
tag commit:        7637a38b4fb9ec21dfb953c1c80a27ec5f389654
PyPI package:      cinder-cvt==1.1.2
Python:            3.12
```

The results programme runs against the installed release wheel rather than a mutable local source checkout.

## 3. Reference-model topology

The general results programme now uses a **zero-clearance bilateral/slotted secondary helix** as a results-local reference topology.

The production signed helix torque/force law, torsional spring, movable-member inertia, and secondary shaft-reaction equations remain intact. The results-local policy removes only the selected-unilateral-flank compression requirement. If the signed reaction changes direction, the opposite slot flank carries the reaction instead of terminating the state.

The reason is methodological: most results are intended to interrogate the belt reduction, closure, hybrid contact, actuator dynamics, and complete system response. They should not be terminated simply by a hardware-specific selected-flank lift-off unless helix contact topology is itself the question.

The next cleanup step is not to invent this policy but to **audit and freeze it across all maintained general studies**. The only intended exception is the dedicated bilateral/slotted-versus-unilateral helix study described below.

## 4. Completed scientific foundation

### 4.1 Mechanical-energy consistency

Status: **DONE / PASS**

The release-level study now supports the conclusion that modeled boundary work, retained stored mechanical energy, continuous slip dissipation, and discrete event losses close to numerical-error scale for the retained mechanics.

Use this as verification of the implemented equations and event accounting, not as evidence that omitted physical loss mechanisms are absent from real hardware.

### 4.2 Mechanical invariants / operating-domain capability

Status: **DONE / PASS**

The study has evolved from a nominal-trajectory audit into a broad challenge of the retained model: static rest; engaged/deadzone structural states; forward and reverse rotation; positive and negative shift motion; both signed single-interface slip directions; all four both-slip quadrants; full geometry-domain checks; belt tension and distributed normal-load admissibility; stop and mechanism reactions; 8x8 closure residuals; and exact hybrid successor states.

A useful qualitative conclusion has emerged: some states are routine and broad, some are valid but transient/narrow, and some candidate states fail because the **retained topology** would need additional physics such as belt slack, contact lift-off, or a different mechanism contact arrangement.

Do not turn this into a claim of exhaustive proof over the continuum of all initial conditions.

### 4.3 Solver convergence

Status: **DONE**

The maintained study now contains a formal `rtol x max_step` sweep, an independent absolute-tolerance sweep, complete state-trajectory error metrics, hybrid transition/signature comparisons, event-time errors, regime-history mismatch, and computational cost measures.

Paper-facing plots can be regenerated from the frozen formal artifacts. The optional dense overnight explorer is supplementary and should not redefine the formal convergence evidence.

### 4.4 Ballew 2015 model-to-model benchmark

Status: **DONE / interpretation recorded**

Two protocols remain important:

1. **force replay**, which is the cleaner comparison of plant response to a prescribed primary clamp-force history;
2. **reconstructed closed loop**, which compares the complete controlled behavior using the published controller information and documented reconstruction assumptions.

The benchmark is useful external context but is not direct experimental validation of CINDER. Closed-loop output similarity must not be interpreted as proof of identical internal plant mechanics.

### 4.5 Actuator dynamics / axial-rotational coupling

Status: **DONE / mature result family**

The actuator study now contains the four-model Baja ablation, component-level dynamic correction measures, coupling-energy/generalized-inertia decomposition, equation-derived quasi-static validity envelopes, controlled transient validation, source-registered commercial-scale sensitivity, and a commercial-secondary mechanism-transplant trajectory demonstration.

The important scientific posture is scale-aware rather than promotional. Small corrections at Baja scale can justify quasi-static reductions there, while larger corrections at other plausible scales show that the retained dynamic coupling is not intrinsically negligible.

## 5. Closure conditioning — current active endpoint

Closure conditioning asks three related but distinct questions.

### A. Specified traction pair

For fixed `(lambda_p, lambda_s)`, CINDER solves the production 8x8 mechanical closure. Where the assembled matrix is nonsingular, the mechanical response is unique.

The finite-lambda conditioning walls observed in maps are properties of the assembled coupled equations, not simple finite-real poles in the isolated regular wrap functions.

### B. Stick-stick closure

When both contacts stick, both traction utilizations are free and the model solves a nonlinear 2x2 residual map.

The present exploratory evidence supports the following working picture:

- roots encountered on ordinary physical trajectories are generally locally regular;
- severe 8x8 conditioning ridges are often excluded by belt/contact/mechanism admissibility before the physical trajectory reaches them;
- the global stick-stick residual map can contain more than one root;
- continuation and manifold work indicate that the extra roots belong to structured, folded continuous solution branches rather than being random numerical optimizer artifacts;
- alternate branches can run toward friction limits, belt-tension/contact limits, or mechanism-admissibility limits.

This is a genuine property of the **retained one-gross-traction-state-per-wrap closure**. It is also a limitation of that reduction: a future spatial contact model may alter or reinterpret this global root structure.

### C. Final missing closure question: mixed stick/slip

The remaining endpoint is the true 1D closure in:

- primary-slip / secondary-stick;
- primary-stick / secondary-slip.

The sliding contact supplies a fixed kinetic traction utilization from its slip direction. Only the sticking contact retains an unknown static traction utilization.

The question is:

> **Can the one-dimensional mixed-contact closure itself become multirooted/folded, or is the observed multiplicity fundamentally associated with having two simultaneously free stick tractions?**

Once both mixed branches are searched and this is answered, closure conditioning should be frozen unless the 1D result reveals a genuinely new mechanism.

## 6. Retained reduced-belt mechanics — next major new result

The belt study should not be framed as proving that CINDER's inextensible one-transport-coordinate belt is the final rubber-belt representation.

The better question is:

> **Within a dynamically closed reduced whole-belt model, which retained transient terms matter, when do they matter, and which coherent reductions are justified?**

The planned sequence is:

### Stage 1 — exact inventory

Trace every transient/inertial contribution in the wrap radial and tangential balances, tension evolution, straight spans, moving span boundaries, whole-belt transport equation, and closed-loop tension compatibility.

### Stage 2 — magnitude/regime audit

Measure the signed contribution of each term with a physically appropriate normalization during ordinary launch, free shift, strong load/backshift, and any contact transition that excites it.

### Stage 3 — coherent reductions

Only after the inventory, remove coherent classes of terms rather than arbitrary individual algebraic pieces. Preserve mechanical/energetic consistency and compare complete trajectories.

All three possible outcomes are useful:

- negligible term -> justified simplification;
- transient-only term -> clearly defined limit of a quasi-static reduction;
- materially important term -> mechanism a reduced model should retain.

This study should also identify where the present reduced representation is being pushed hardest and therefore motivate the next-generation spatial/contact model.

## 7. Mechanism-resolved launch / hill result

The launch-hill infrastructure already exists. The remaining work is to make it a scientific explanation rather than merely a set of plots.

The intended causal spine is:

```text
external road/wheel load
-> secondary shaft demand
-> helix, spring, and belt axial reactions
-> normal loads / traction utilization
-> movable-sheave acceleration
-> ratio / backshift
-> shaft and vehicle response
```

The final case should remain mechanically interpretable and should not become a tuning optimization exercise.

Use the canonical bilateral/slotted helix topology here.

## 8. Bilateral/slotted versus unilateral helix — final dedicated design study

This study asks a stronger question than simple admissibility:

> **When the demanded helix reaction reverses sign, does bilateral/slotted support materially change transient CVT performance compared with a conventional selected unilateral flank that can lose contact?**

This is scientifically interesting because CINDER solves the movable secondary member as a free body. The required helix reaction is therefore a solved contact reaction rather than merely a prescribed force contribution, so the model can detect when a selected contact flank would need to pull.

### Bilateral/slotted comparison model

Support either reaction sign with zero clearance. A sign reversal transfers load directly to the opposite slot flank and preserves the helix kinematic coupling.

### Ideal unilateral comparison model

While the chosen flank is engaged, require compressive contact.

If the required reaction falls to zero and would reverse:

- release that helix contact;
- set the helix contact reaction to zero;
- release the corresponding kinematic constraint.

For the first-order study, omit detailed backlash traversal, impact, friction, and opposite-flank capture. These are real hardware refinements but are not required to isolate the first-order consequence of losing bidirectional support.

A force-clipped-but-kinematically-constrained variant may be useful as a sensitivity check, but it should not be treated as the primary physical unilateral model.

### Cases

Use at least:

1. normal forward operation;
2. a sudden large wheel/secondary load;
3. reverse power flow such as engine braking or imposed negative secondary torque.

### Outputs / design measures

Compare the signed helix reaction, helix contact state, secondary axial motion, spring/belt/helix force balance, normal resultant, shaft torque/speed, CVT ratio, vehicle response, and traction state.

Also measure how much opposite-flank support the bilateral trajectory demands, for example by the fraction of time with opposite-signed reaction and an impulse-like integral of that reaction.

Do not assume the slotted design will be universally better. A valid result could show improved transient support, excessive reverse-flow axial response, or negligible differences except in extreme/reversed operation.

## 9. Scientific positioning of the reduced model

The paper should not defend every reduction as permanent.

A useful high-level framing is:

> **CINDER closes the reduced problem. The results show what that closure enables, which retained mechanics matter, and where the reduction itself begins to show its limits.**

The present model gains system-level completeness by retaining a relatively compact contact and belt representation:

```text
one gross traction state per pulley wrap
one global belt transport coordinate
inextensible whole-belt geometry
prescribed contact/wrap structure within each active topology
```

The natural next research step is to spend additional complexity on spatial resolution:

```text
lambda_j
    -> lambda_j(theta,t)

one belt transport speed
    -> local belt velocity / strain transport

prescribed full contact
    -> solution-dependent contact extent / lift-off
```

The root-structure and retained-belt findings should therefore be stated with explicit jurisdiction: they are discoveries inside the current reduced model, and they help indicate what a higher-fidelity successor should resolve.

## 10. Pre-writing exit sequence

The remaining execution order at this snapshot is:

1. finish the mixed-contact 1D closure study;
2. audit and freeze the bilateral/slotted reference topology across maintained studies;
3. complete the retained-belt term inventory, magnitude audit, and coherent reductions;
4. refine the launch/hill study into the mechanism-resolved explanatory result;
5. complete the bilateral/slotted-versus-unilateral helix performance comparison;
6. clean and consolidate the results tree;
7. update the literature/novelty matrix;
8. decide the final Chapter 4 high-level structure and story;
9. write the results section.

The explicit stop rule is important: do not invent another major result family after these unless one of them reveals a real missing requirement.

## 11. Likely Chapter 4 logic — not frozen

The exact subsection order should wait for the remaining evidence, but the likely high-level scientific flow is now clearer:

```text
model / numerical credibility
-> external model comparison
-> consequences of retained dynamic mechanics
-> mechanism-resolved system behavior
-> design insight and limits of the reduction
```

Verification studies may ultimately be compressed or partly moved to appendices/repository artifacts so the paper does not become dominated by numerical infrastructure.

The actuator, reduced-belt, mechanism-resolved hill, and helix-topology results are the strongest candidates to carry the scientific narrative after credibility has been established.

## 12. Claim boundaries to preserve

- Energy, invariants, closure conditioning, and convergence are **verification**, not physical validation.
- Ballew is a **model-to-model comparison**, not direct experimental validation.
- Multiple algebraic roots in the reduced stick-stick closure are not automatically multiple real-belt physical states.
- Topology inadmissibility can mean the retained reduction needs another degree of freedom, not that real hardware behavior is impossible.
- The bilateral/slotted results topology is a deliberate reference-model choice, not a universal hardware recommendation.
- The unilateral helix comparison is idealized unless backlash, impact, clearance, and friction are explicitly added.
- Retained reduced-belt terms should be compared carefully with prior literature before strong novelty wording is frozen.
- “First model to…” or equivalent priority claims require a final dedicated literature check.
- A small effect can still be a scientifically useful result when it establishes the validity range of a simpler model.

## 13. Handoff point

If work resumes from this snapshot, the immediate task is:

> **Finish the true one-dimensional mixed stick/slip closure search and use it to close the closure-conditioning study.**

After that, perform the slotted-reference-model audit before beginning the retained-belt result family.
