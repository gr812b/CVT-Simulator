# CINDER Results Program — Context Snapshot
**Status date:** 2026-09-09  
**Purpose:** Preserve the current reasoning, evidence, open questions, and planned results program before additional exploratory studies are run.

## 1. Purpose of the final results section

The results section should build confidence in CINDER at four distinct levels. These should not be conflated.

### A. Mechanical and numerical correctness
Question: **Did the derivation make it into the implementation correctly, and are the reported trajectories numerical solutions of those equations rather than solver artifacts?**

Candidate evidence:
- global mechanical-energy balance;
- event-by-event impact/capture energy and momentum audits;
- belt-loop/geometric closure residuals;
- governing-equation residuals;
- contact admissibility checks;
- unilateral stop-reaction admissibility;
- solver refinement / convergence;
- difficult hybrid-trajectory stability tests.

Interpretation boundary:
- verification establishes internal consistency;
- it does **not** establish that every modeling assumption matches reality.

### B. Mechanism-resolved intuitive example
Question: **Does the complete machine evolve through a physically understandable causal chain?**

Preferred direction:
- use one strong reference transient rather than many tuning cases;
- likely a normal launch plus a controlled load disturbance such as a hill/load step;
- follow the mechanism in causal order:
  external load / engine torque
  → actuator forces
  → belt normal loads / contact state
  → transmitted torque
  → shift motion
  → shaft / vehicle response.

This section should both:
1. make the model mechanically believable; and
2. teach the reader how a mechanically actuated CVT actually behaves.

The old Chapter 4 is obsolete numerically but remains useful as a storytelling template.

### C. Ballew comparison
Question: **Does an independently architected transient rubber-belt model produce comparable macroscopic dynamics?**

Current benchmark structure:
1. **Force replay:** impose Ballew's digitized primary clamp-force history on CINDER and compare shaft speeds / ratio.
2. **Reconstructed closed loop:** reconstruct Ballew's published PI + feed-forward control around unchanged CINDER and compare both systems' outputs.

Current provisional interpretation from CINDER 1.0.0 work:
- reconstructed closed-loop shaft speed / ratio agreement was roughly 3–5% RMSE;
- primary clamp-force history differed much more strongly (~46% RMSE);
- direct clamp-force replay produced substantially larger plant-response disagreement.

Important interpretation:
- this is a **model-to-model comparison**, not direct experimental validation;
- good closed-loop agreement does not prove identical plant mechanics because the controller can compensate for plant differences;
- force replay is the cleaner plant-to-plant comparison;
- disagreement may itself reveal an important architectural difference between reduced whole-belt and discretized elastic-belt models.

Ballew remains valuable because his model sits in the Julió–Plante discretized rubber-belt lineage, which has experimental grounding.

### D. New mechanics / scientific payoff
Question: **What does CINDER let us quantify or explain that prior formulations could not isolate as cleanly?**

Current candidate result families:
1. dynamic actuator inertia and axial–rotational coupling;
2. retained reduced-belt transient terms and potential model reductions;
3. fully hybrid operation across engagement, stops, stick/slip, backshift, and disengagement.

These are not frozen claims. Each must be tested against both simulation evidence and prior literature.

---

## 2. Current repo/results architecture

The results tree is intentionally release-scoped.

Existing structure:
- `results/cinder-v1.0.0/`
- frozen release-local defaults;
- study-local overrides / extension points;
- generated artifacts derived reproducibly from the frozen release.

Design principle:
- old result studies must never be silently migrated to newer mechanics;
- each new CINDER release should receive a sibling results directory.

Current `develop` package version:
- `cinder-cvt==1.1.1`

Therefore the next research baseline should become a new release-scoped results environment once the exact release/tag/wheel is confirmed.

Likely immediate migration work:
- create `results/cinder-v1.1.1/` or the actual final release sibling;
- copy / regenerate authoritative Baja default case from that release;
- port Ballew study without mutating 1.0.0 provenance;
- port launch/hill study;
- migrate correctness studies;
- migrate selected actuator / coupling studies from `launchTools`;
- rerun and reinterpret everything against the final mechanics.

---

## 3. Correctness / verification program

### Already present
CINDER already has a strong 45 s energy audit in the current source tree. The previously recorded audit showed:
- net external work ≈ 78.1598 kJ;
- kinetic-slip dissipation ≈ 2.16145 kJ;
- discrete capture/stop dissipation ≈ 0.0579 J;
- stored mechanical-energy increase ≈ 75.9985 kJ;
- residual ≈ −0.256 J;
- normalized residual ≈ 0.000327% of net external work.

Current impact/capture code also records:
- pre/post kinetic energy;
- dissipated energy;
- post-event constraint residual;
- generalized momentum residual.

### Verification categories to formalize

#### Energetic
- cumulative primary boundary work;
- cumulative secondary / road work;
- stored kinetic + potential energy;
- continuous kinetic-slip dissipation;
- discrete impact/capture dissipation;
- global residual.

#### Geometric / kinematic
- belt-length closure;
- correct one-sided geometry at engagement;
- active stop constraints;
- deadzone secondary-belt lock;
- sticking velocity constraints.

#### Dynamic
- 6×6 closure residuals;
- sticking residuals;
- reconstructed stop reactions;
- impact momentum projection residuals.

#### Contact / hybrid
- `N_p >= 0`, `N_s >= 0`;
- static traction within `|lambda_j| <= mu_s`;
- kinetic branch sign consistency;
- no energy creation by kinetic friction;
- no tensile unilateral stop reaction;
- post-event velocity constraints satisfied.

#### Numerical
- solver tolerance / max-step refinement;
- accepted internal-step statistics;
- difficult hybrid case;
- compare practical settings to a tight CINDER-only reference;
- avoid claiming numerical convergence as physical validation.

---

## 4. Canonical intuitive transient

Preferred study:
- one ordinary Baja launch;
- followed by a controlled load disturbance, likely grade or secondary-load increase.

Desired plot / explanation order:
1. shift position / ratio and structural/contact regime;
2. primary and secondary shaft speeds / vehicle speed;
3. actuator contributions;
4. movable-sheave axial force balances;
5. normal resultants;
6. traction utilizations and relative contact speeds;
7. belt torque / boundary torque;
8. load disturbance and resulting backshift or recovery.

Narrative goal:
**show the cause, then the internal reaction, then the system consequence.**

Avoid making this primarily a tuning contest.

---

## 5. Ballew benchmark program

### Existing protocols
#### Force replay
Use Ballew Fig. 45 primary axial force as an input to CINDER.
Compare:
- primary speed;
- secondary speed;
- ratio.

Purpose:
- isolate clamp-force → macroscopic plant-response behavior.

#### Reconstructed closed loop
Use only Ballew-published controller information plus documented reconstruction assumptions.
Compare:
- primary speed;
- secondary speed;
- ratio;
- primary force as an output diagnostic.

Purpose:
- compare complete controlled macroscopic behavior.

### Re-run requirements
- port benchmark to final CINDER release;
- preserve original v1.0.0 benchmark untouched;
- regenerate digitization-derived reference inputs deterministically;
- rerun convergence around the new nominal setup;
- rerun broad numerical stability sweep if needed;
- compare old vs new benchmark metrics;
- investigate any changed disagreement rather than forcing the old interpretation.

### Interpretation boundary
Never call this direct CINDER experimental validation.

---

## 6. Dynamic actuator inertia / axial–rotational coupling

This is already one of the strongest exploratory result families.

### Existing study design
`run_dynamic_actuator_ablation.py` separates two questions.

#### A. Same-state constitutive comparison
Evaluate dynamic and quasi-static actuator laws:
- at the same state;
- with the same solved closure unknowns.

This isolates the instantaneous force/torque correction created by retained dynamic terms.

#### B. Independent trajectory consequence
Integrate four mechanically consistent variants:
- full dynamic;
- quasi-static flyweight;
- quasi-static helix;
- both quasi-static.

Important:
- removed mechanism-relative inertia is returned to the classical shaft inertia;
- mass is not simply deleted.

### Existing coupling-energy study
`run_coupling_energy_flow.py` exposes:
- flyweight shaft-axis kinetic energy;
- flyweight pivot kinetic energy;
- configuration power;
- helix torsional spring energy;
- movable-secondary rotational kinetic energy;
- shaft / relative / cross kinetic decomposition;
- effective generalized shift-mass contributions.

### Existing helix sensitivity study
`run_helix_inertia_torque_scaling_sweep.py` varies:
- secondary movable-member rotational inertia;
- imposed secondary torque.

It asks when dynamic helix corrections exceed:
- 5%;
- 10%;
- 20%;
- 50%.

### Scientific question
Not “is reflected inertia always important?”

Instead:
- how large is it in the actual Baja machine?
- which term dominates?
- when is a quasi-static actuator approximation justified?
- under what inertia/load/shift-rate scales does it become important?

A small Baja-baseline effect is still a useful result.

---

## 7. Reduced-belt transient terms

This remains the least complete and most exploratory part.

CINDER retains:
- one global belt transport speed;
- pulley-wrap transient terms;
- radial acceleration;
- changing-radius tangential acceleration;
- straight-span inertia;
- moving span-boundary momentum transport;
- analytical closed-loop tension compatibility.

Prior literature retains overlapping subsets, so novelty must be worded carefully.

### Proposed study sequence

#### Stage 1: term inventory
Identify every belt-related inertial / transient contribution appearing in:
- wrap radial balance;
- wrap tangential balance;
- wrap tension ODE;
- straight-span balances;
- whole-belt transport equation;
- closed-loop tension compatibility.

#### Stage 2: magnitude audit
For each term:
- record time history;
- normalize against an appropriate force / tension scale;
- inspect launch, backshift, fast load transient, and slip transition.

#### Stage 3: coherent model reductions
Only after magnitude mapping:
- construct mechanically consistent reduced variants;
- remove one class of term at a time where possible;
- rerun energy audit;
- compare trajectory changes.

Questions:
- which terms are negligible during ordinary operation?
- which appear only during rapid shift / engagement?
- which previous simplifications are actually justified?
- which omitted term creates a meaningful trajectory error?

---

## 8. Hybrid-regime capability

CINDER's scientific value is not merely “it can simulate slip.”

The stronger capability is one initial-value problem moving between mechanically distinct arrangements whose transitions emerge from admissibility conditions.

Relevant structural/contact behavior includes:
- primary fully open stop;
- free deadzone;
- first belt engagement;
- engaged low-ratio seat;
- free engaged shift;
- upper primary stop;
- primary/secondary sticking;
- mixed stick-slip;
- both-slip where admissible;
- stop release;
- load-induced backshift;
- primary separation / deadzone entry;
- deadzone re-engagement.

### Candidate controlled scenarios
- normal launch;
- sudden load / grade increase;
- unloading / backshift;
- upper-stop arrival;
- contact traction limit crossing;
- engine-braking or reversed torque case if useful.

### Scientific questions
- which contact loses traction first?
- when does a low-ratio seat hold or release?
- what happens to momentum at first contact?
- does a contact-state change immediately invalidate a stop reaction?
- how much energy is lost in rigid capture events?
- which transitions matter on a normal vehicle trajectory versus only stress cases?

Avoid “rainbow mode plot” as the entire result. Use specific physical questions.

---

## 9. Literature-comparison matrix to maintain

For every candidate novelty result, track:
- phenomenon;
- source;
- rubber / metal / chain;
- steady / transient;
- mechanical / hydraulic actuation;
- belt or chain inertia retained;
- axial–rotational coupling retained;
- local slip treatment;
- hybrid contact-state switching;
- shift stops / engagement represented;
- experimental comparison;
- what CINDER adds;
- claim strength.

Priority sources already identified:
- Gerbert;
- Kim & Kim;
- Sorge;
- Cammalleri / Sorge;
- Julió & Plante;
- Ballew;
- Kong & Parker;
- Duan et al.;
- CMM / Carbone et al.;
- experimental rubber V-belt comparison papers.

---

## 10. Provisional final Chapter 4 spine

Not frozen.

Likely shape after the exploratory work:

### 4.1 Mechanical and numerical verification
Internal correctness and solver independence.

### 4.2 Comparison with an established transient rubber-belt model
Ballew benchmark.

### 4.3 Mechanism-resolved reference transient
One intuitive launch / load case.

### 4.4 Consequences of retained dynamic mechanics
Only the result families that survive exploratory testing:
- actuator inertia / coupling;
- reduced-belt transient terms;
- hybrid-regime findings.

The final order should emerge from evidence, not be imposed before the studies are complete.

---

## 11. Immediate execution order

1. Preserve this context snapshot and working ledger.
2. Resolve the current Section 3.6 / transition compatibility concern before freezing new results.
3. Confirm exact final CINDER release version/tag.
4. Create new release-scoped results directory.
5. Port and rerun Ballew.
6. Port/rerun old reference studies.
7. Promote correctness audit into results tree.
8. Verify all migrated results.
9. Build canonical intuitive transient.
10. Work through new mechanics one family at a time.
11. Maintain literature matrix throughout.
12. Draft Chapter 4 only after the evidence stabilizes.

---

## 12. 2026-09-09 transition-compatibility audit: wrap radial belt kinetic modes

### Finding

The concern about changing-radius belt motion at Section 3.6 transitions is real, but narrowly located.

The **continuous engaged equations are already correct with respect to the retained Section 3.4 wrap kinematics**. They include:
- radial wrap acceleration through \(r_j\ddot r_j\);
- changing-radius tangential acceleration through \(\dot r_j v_b\);
- \(r_j'(s)\dot s\) in the differentiated sticking/contact compatibility.

The current Section 3.6 transition framework is also structurally correct:
- it uses a mass-metric momentum projection;
- it uses different deadzone- and engaged-side kinematic maps;
- it does not copy \(\dot s\) unchanged through engagement.

However, the implementation of the transition kinetic map currently represents the belt only with the global transport mode \(v_b\). It does **not** include the radial velocity carried by belt mass on each engaged pulley wrap,

\[
\dot r_j = r_j'(s)\dot s.
\]

This is inconsistent with the Section 3.4 velocity field

\[
\mathbf v_{b,j}
=
\dot r_j\,\hat{\mathbf e}_r
+
v_b\,\hat{\mathbf e}_\theta.
\]

### Missing kinetic modes

For each pulley wrap, the retained model implies the instantaneous wrap mass

\[
m_{\mathrm{wrap},j}
=
\rho_b A_b r_{j,\mathrm{cm}}\phi_j.
\]

The Section 3.6 physical-velocity map should therefore include, in addition to the existing full-belt transport mode,

\[
\mathbf j_{b,r,p}
=
\begin{bmatrix}
0&0&0&r_p'
\end{bmatrix},
\qquad
\mathbf j_{b,r,s}
=
\begin{bmatrix}
0&0&0&r_s'
\end{bmatrix},
\]

with inertia weights \(m_{\mathrm{wrap},p}\) and \(m_{\mathrm{wrap},s}\).

This adds the retained radial wrap kinetic energy

\[
\mathcal T_{b,r}
=
\frac12
\left[
m_{\mathrm{wrap},p}(r_p')^2
+
m_{\mathrm{wrap},s}(r_s')^2
\right]
\dot s^2.
\]

The belt transport mode \(m_b v_b^2/2\) remains unchanged. Using the same belt material in orthogonal transport and radial velocity modes is not double-counting: each mode accounts for a different component of the velocity field already assumed in Section 3.4.

### Preliminary magnitude check

Using the current Baja geometry and belt properties, the omitted wrap-radial contribution corresponds approximately to an additional generalized shift inertia of:
- ~0.50 kg near engagement;
- ~0.67 kg around mid-shift;
- ~0.84 kg near maximum shift.

For comparison, the literal primary + secondary moving-sheave translational contribution is approximately:
- ~1.43 kg near engagement;
- ~1.59 kg around mid-shift;
- ~1.85 kg near maximum shift.

Thus the wrap-radial term is roughly 35–45% of the literal sheave translational contribution before flyweight/helix reflected terms are considered. It is therefore not defensible to assume it is negligible without testing.

These are preliminary analytical scale estimates, not simulation results.

### Minimal implementation fix

In `cvt_impact._physical_velocity_map`:
1. compute belt line density \(q=\rho_bA_b\);
2. compute each engaged wrap mass \(q r_{j,\mathrm{cm}}\phi_j\);
3. add one physical radial velocity row per wrap using \(r_j'(s)\);
4. allow the deadzone topology to use the same component basis with zero one-sided radius derivatives;
5. leave the existing global belt transport row unchanged.

Because `kinetic_energy_for_topology()` uses the same physical-velocity map, the stored-energy audit will automatically acquire the same radial kinetic energy.

### Required regression / acceptance checks

1. Add a unit test for the radial wrap kinetic-energy contribution.
2. Re-run the engagement capture test.
3. Re-run upper/lower stop impact tests.
4. Re-run the full mechanical-energy audit.
5. Inspect the **time-resolved** energy residual through shifting, not only the final endpoint residual.
6. If adding the missing storage term exposes a residual during continuous shifting, audit the moving wrap-boundary / seating-unseating energy flux before freezing the results release.
7. Only after these checks should the next release-scoped results baseline be frozen.

### Manuscript correction

Section 3.6 does not need a new transition law. Its existing KKT/mass-metric derivation is the right framework.

It should be amended so that the physical velocity map explicitly includes:
- full-belt tangential transport;
- primary-wrap radial motion;
- secondary-wrap radial motion;
alongside the shaft, sheave, flyweight, and helix modes already described.

The no-slip velocity constraint remains

\[
v_{\mathrm{rel},j}=v_b-r_j\omega_j=0.
\]

No \(r_j'\dot s\) term should be inserted into that velocity-level relation. The changing-radius term appears only after differentiation,

\[
a_{\mathrm{rel},j}
=
\dot v_b
-r_j\dot\omega_j
-r_j'\dot s\,\omega_j,
\]

which the current smooth contact implementation already uses.

