# CINDER Results Working Ledger
**Status:** active / exploratory  
**Updated:** 2026-09-09  
**Rule:** Record the scientific question first. Add findings only after a reproducible study exists. Nothing here is a frozen manuscript claim unless explicitly marked as such.

## 1. Results-program status

| Item | Status | Next action |
|---|---|---|
| Results baseline | **DONE** | CINDER `v1.1.2` is the frozen mechanics release for the current results program. |
| Release-scoped results tree | **DONE** | Continue under `results/cinder-v1.1.2/`; do not mutate prior release results. |
| Preserve `cinder-v1.0.0` | **LOCKED** | Never silently migrate old results or overwrite their provenance. |
| Ballew model-to-model comparison | **DONE / INTERPRETATION RECORDED** | Return during Chapter 4 drafting; do not present as direct experimental validation. |
| Mechanical-energy consistency | **DONE / PASS** | Keep as release-level verification evidence. |
| Canonical launch / hill narrative | **DEFERRED** | Revisit later when assembling the mechanism-resolved results narrative. |
| Actuator dynamics / coupling | **PROMOTED — AWAITING v1.1.2 RUN / INTERPRETATION** | Run canonical baseline ablation + coupling-energy study; retain stress/scaling only as exploratory infrastructure. |
| Mechanical invariants | **PLANNED** | Build release-scoped invariant audit. |
| Closure conditioning | **PLANNED** | Promote and extend residual/Jacobian/conditioning work across representative states. |
| Solver convergence | **PLANNED** | Build controlled tolerance/max-step sweeps against a tight reference trajectory. |
| Reduced-belt transient-term inventory | **OPEN NEW RESEARCH** | Begin after verification studies are complete. |
| Coherent reduced-belt ablations | **OPEN** | Only after term inventory identifies meaningful candidate reductions. |
| Targeted hybrid-regime studies | **LATER** | Build from specific physical questions, not mode-count demonstrations. |

## 2. Reproducibility / implementation section for the final results chapter

Near the beginning of the results chapter, include a short reproducibility and implementation section that:

- identifies the exact CINDER release/tag used for all results;
- links to the public code and release-scoped results tree;
- records frozen input documents, study-specific overrides, solver settings, and generated artifacts;
- distinguishes derivation-level presentation from implementation-level numerical organization.

One implementation note should explain that the manuscript may present a reduced mechanical response system for clarity, while the production implementation solves the complete instantaneous closure in an **8×8 affine system** over

\[
[\dot\omega_p,\ \dot\omega_s,\ \dot v_b,\ \ddot s,\ \tau_p,\ \tau_s,\ N_p,\ N_s],
\]

with contact-state closure handled around that solve. The implementation structure is chosen for numerical robustness and direct audibility of the complete coupled mechanics; it does not change the physical equations represented by the derivation.

Keep distinct:
- **8×8 mechanical-closure conditioning**, and
- **2×2 stick-root conditioning** in \((\lambda_p,\lambda_s)\).

## 3. Completed verification foundation

### 3.1 Mechanical-energy consistency — DONE

Question: **Does modeled external work equal retained stored-energy change plus explicitly modeled irreversible losses, up to numerical error?**

Current conclusion:
- the material structural energy inconsistency identified during development was corrected before `v1.1.2`;
- exact event/capture energy accounting closes to numerical precision;
- global continuous-energy residual is sub-ppm relative to energy throughput;
- tighter ODE integration moves the residual through zero while preserving the same hybrid trajectory;
- remaining discrepancy is numerical-error scale, not evidence of another material missing physical power channel.

Interpretation boundary: this verifies the retained mechanics; it does not prove every omitted physical effect is negligible in reality.

### 3.2 Ballew comparison — DONE

Question: **Does an independently architected transient rubber-belt model produce comparable macroscopic behavior under matched protocols?**

Current interpretation:
- reconstructed closed-loop primary/secondary shaft-speed response agrees reasonably well;
- primary clamp-force history differs strongly;
- direct Ballew clamp-force replay produces much larger plant-response disagreement;
- CINDER's internal geometric ratio can differ strongly from its shaft-speed ratio during the reconstructed closed-loop benchmark.

Interpretation boundary:
- model-to-model comparison only;
- good controlled-output agreement does not imply identical internal plant mechanics;
- force replay is the cleaner plant-mapping comparison;
- do not describe this as direct experimental validation of CINDER.

## 4. Verification studies still to build

The verification package should contain four conceptually distinct studies:

1. `energy-consistency/` — **DONE**
2. `mechanical-invariants/`
3. `closure-conditioning/`
4. `solver-convergence/`

These remain separate studies even if they later appear together in one manuscript section.

### 4.1 Mechanical invariants

Question: **Does the integrated trajectory remain on the mechanical and admissibility manifolds required by the formulation?**

Audit at minimum:

\[
L_{\rm belt}\text{ closure},
\qquad
A\mathbf{x}-\mathbf b\text{ closure-equation residuals},
\]

\[
|v_{\rm rel,j}|\approx0
\quad\text{during declared stick},
\]

\[
|a_{\rm rel,j}|\approx0
\quad\text{for acceleration-level stick compatibility where appropriate},
\]

\[
|\lambda_j|\le\mu_s
\quad\text{for static contact},
\]

kinetic-slip direction/sign consistency,

\[
N_p\ge0,\qquad N_s\ge0,
\]

and unilateral stop admissibility.

Also record:
- active kinematic-constraint residuals;
- closure matrix rank;
- post-transition constraint residuals not already covered by the energy study.

Preferred headline artifact: a compact table of the worst observed violation over the complete reference trajectory, with time histories only where they reveal useful structure.

Interpretation: energy closure is global bookkeeping; the invariant audit establishes local equation/constraint/admissibility consistency.

### 4.2 Closure conditioning

Question: **Is the instantaneous algebraic closure well posed and numerically well conditioned over the physical states and traction-utilization regions CINDER actually encounters?**

Keep two levels distinct.

#### A. 8×8 mechanical closure

For each sampled trial pair and actual solved trajectory state, record:

\[
\operatorname{rank}(A),\qquad
\kappa(A),\qquad
\kappa_{\rm scaled}(A),
\]

and post-solve equation residuals.

Determine:
- where conditioning worsens;
- whether those regions correspond to identifiable geometric or dynamic mechanisms;
- whether actual trajectories approach those regions;
- whether conditioning changes systematically with shift position, shaft speed, loading, or contact state.

#### B. 2×2 stick-root map

Define

\[
\mathbf R(\lambda_p,\lambda_s)
=
\begin{bmatrix}
R_p\\
R_s
\end{bmatrix},
\qquad
J_R
=
\frac{\partial(R_p,R_s)}{\partial(\lambda_p,\lambda_s)}.
\]

Do not use only \(\det J_R\) as the formal conditioning measure. Record:

\[
\sigma_{\min}(J_R),
\qquad
\sigma_{\max}(J_R),
\qquad
\kappa(J_R)=\frac{\sigma_{\max}}{\sigma_{\min}},
\]

along with the signed determinant for geometric interpretation.

Map classes:

1. **Baseline physical Coulomb box** — actual baseline friction coefficients.
2. **Expanded physically plausible utilization domain** — broader than the baseline Coulomb box so the residual geometry can be studied independently of one chosen friction coefficient. This is a mathematical/parametric diagnostic, not a baseline admissible domain.
3. **Broad diagnostic domain** — much larger signed domain retained only to expose singular/asymptotic structure; not physically admissible operation.

Representative states should include at least:
- low ratio / near engagement seat;
- active mid-shift;
- late shift / near upper range;
- backshift or load-disturbed state if available;
- optionally a stress state that approaches poor conditioning.

Additional checks:
- multi-start root solve from a grid of initial guesses inside the admissible domain;
- root uniqueness / convergence basin;
- distance of actual solved \((\lambda_p,\lambda_s)\) from poorly conditioned regions.

Scientific goal: explain **why** the residual geometry develops valleys, steep walls, asymptotes, or conditioning spikes. Candidate mechanisms to inspect include:
- normal-resultant closure denominators;
- wrap/tension exponentials;
- near-degenerate pulley/contact leverage;
- geometry-dependent radius ratios;
- actuator gains;
- traction values that drive one solved normal resultant toward a limiting or nonphysical value.

Any observed asymptote or spike should be traced back to the assembled equations before becoming a manuscript result.

### 4.3 Solver convergence

Question: **Are reported trajectories properties of the equations rather than artifacts of LSODA tolerances or maximum step size?**

Build one very tight reference trajectory.

Primary sweep:
- vary `rtol` logarithmically over a useful range;
- vary `max_step` over a useful range;
- initially tie `atol` to `rtol` with the ratio used by the current studies.

Suggested broad grid:

\[
r_{\rm tol}=10^{-2},\ 3\times10^{-3},\ 10^{-3},\ 3\times10^{-4},\ldots,3\times10^{-6},
\]

\[
\Delta t_{\max}=100,\ 50,\ 20,\ 10,\ 5\ {\rm ms}.
\]

Then perform a smaller independent `atol` sensitivity sweep because the state vector contains quantities with very different dimensional scales.

Compare every run to the tight reference using:
- RMS normalized trajectory error per state;
- maximum normalized trajectory error;
- final-state error;
- transition-sequence agreement;
- corresponding event-time error;
- fraction of time with contact/regime mismatch;
- transition count;
- runtime and function-evaluation cost if available.

Preferred figures:
1. accuracy heatmap over `rtol × max_step`;
2. hybrid-sequence/stability map over the same grid;
3. accuracy-vs-cost curve;
4. absolute-tolerance sensitivity plot.

Desired conclusion: identify a region where further solver tightening produces negligible trajectory change but continued computational cost.

## 5. Actuator-dynamics scientific program

Treat the flyweight and helix work as **one study family**:

```text
studies/actuator-dynamics/
```

Scientific question: **What changes when the primary flyweight and secondary helix mechanisms are treated dynamically rather than quasi-statically, and under what physical scales do those corrections matter?**

Do not split the study by primary vs secondary. The two mechanisms are complementary axial–rotational couplings in the same machine.

### 5.1 Baseline ablation — promote directly

Compare four mechanically consistent variants:
- full dynamic;
- quasi-static flyweight;
- quasi-static helix;
- both quasi-static.

Preserve the current rule that removed mechanism-relative inertia is returned to the classical shaft inertia rather than deleted.

Two complementary comparisons:

#### A. Same-state constitutive comparison
Evaluate full and quasi-static actuator laws at the same state using the same solved full-model closure unknowns. This isolates the instantaneous dynamic correction in actuator force/torque.

#### B. Independent trajectory consequence
Integrate all four models independently and compare:
- clamp force;
- contact normal resultants;
- traction utilization;
- shift acceleration / speed / position;
- shaft speeds;
- ratio;
- regime history where relevant.

### 5.2 Coupling-energy decomposition — promote as explanatory sub-experiment

Keep this inside the actuator-dynamics study rather than as a separate scientific study.

Primary flyweight:
- shaft-axis kinetic energy;
- pivot/mechanism kinetic energy;
- configuration power;
- effective generalized shift-inertia contribution.

Secondary helix:
- torsional spring energy;
- movable-member total rotational kinetic energy;
- shaft / cross / relative-motion decomposition;
- effective generalized shift-inertia contribution;
- dynamic torque/clamp correction decomposition.

Purpose: **ablation says whether the terms matter; energy/coupling decomposition explains why.**

### 5.3 Off-baseline exploration — redesign before final promotion

The existing stress-search and inertia/torque scaling tools are useful exploratory infrastructure, but their current parameter sweeps should not automatically become final results.

Before coding final off-baseline experiments, define explicit scientific questions.

#### Primary flyweight coupling
- Which combination of shaft acceleration, shift speed/acceleration, flyweight inertia gradient, and mechanism inertia controls departure from quasi-static behavior?
- At what rate of speed/shift change does the dynamic correction become a specified fraction of the quasi-static flyweight force?
- Does the correction primarily alter instantaneous force prediction, trajectory evolution, or contact-state switching?

#### Secondary helix coupling
- Which combination of movable-member inertia, secondary shaft acceleration, shift acceleration, helix motion ratio, and applied torque controls the dynamic correction?
- When do the \(\dot\omega_s\), \(\ddot s\), and curvature contributions reinforce or cancel?
- What is the boundary between a quasi-static helix approximation and materially dynamic behavior?

Preferred approach:
1. derive the controlling terms from the equations;
2. identify meaningful normalized correction measures;
3. choose sweeps around those measures rather than arbitrary large parameter grids;
4. use a small number of controlled families where only one physical scale changes at a time;
5. validate selected threshold-crossing cases with full independent trajectories.

Potential final outputs:
- baseline correction magnitude;
- dimensionless or scaled correction maps;
- threshold curves with a clear physical interpretation;
- representative trajectories on either side of a quasi-static-validity boundary.

The old brute-force stress search may remain useful for discovering interesting regions, but it should serve **experiment design**, not define the final scientific result by itself.

## 6. Reduced-belt transient mechanics — next major new research family

Begin only after the remaining verification studies are complete.

### Stage 1 — exact term inventory
Identify every retained transient/inertial contribution in:
- wrap radial balance;
- wrap tangential balance;
- wrap tension evolution;
- straight-span balances;
- moving-span-boundary momentum transport;
- whole-belt transport equation;
- closed-loop tension compatibility.

### Stage 2 — magnitude maps
For each term:
- record time history;
- normalize against the appropriate local force/tension/power scale;
- inspect at least ordinary launch, active shift, backshift/load transient, and slip transition.

### Stage 3 — coherent reductions
Only after magnitude mapping:
- remove one physically coherent class of terms at a time;
- preserve energy/mechanical consistency;
- rerun verification;
- compare trajectories.

Questions:
- which terms are negligible in ordinary operation?
- which appear only in rapid transients?
- which classical simplifications are justified?
- which omitted terms cause meaningful trajectory differences?

## 7. Hybrid-regime studies — later targeted work

Do not build a mode-count result. Use targeted physical questions such as:
- which contact loses traction first under controlled load increase?
- what releases the low-ratio seat?
- what happens to momentum and energy at first engagement?
- when does a stop reaction become inadmissible?
- how does a load transient produce backshift?
- which transitions occur in ordinary operation versus only stress cases?

## 8. Interpretation boundaries

- Energy / invariants / conditioning / convergence = **verification**, not physical validation.
- Ballew = **model-to-model comparison**, not direct experimental validation.
- Good closed-loop agreement does not prove identical plant mechanics.
- A small actuator-dynamics effect at Baja scale can still meaningfully justify a quasi-static reduction.
- Retaining a physical term is not automatically novel; literature comparison is required before novelty claims.
- Off-baseline sweeps must answer explicit physical questions rather than merely search a large parameter space.
- Hybrid capability should be presented through causal mechanical questions, not a catalogue of modes.
- Broad lambda-domain maps beyond the Coulomb box are mathematical diagnostics, not baseline admissible states.

## 9. Immediate execution order

1. Preserve `CINDER_RESULTS_CONTEXT_2026-09-09.md` unchanged as a historical snapshot.
2. Replace this working ledger with the current version.
3. **DONE: promotion packaged.** Run and interpret the canonical **baseline actuator ablation + coupling-energy decomposition** in `actuator-dynamics/`.
4. Keep existing stress/scaling infrastructure available, but redesign the final off-baseline actuator experiments before promoting them as final results.
5. Build `mechanical-invariants/`.
6. Build `closure-conditioning/` with 8×8 closure metrics, 2×2 stick-root singular values/conditioning, multiple lambda-domain scales, representative states, multi-start root tests, and equation-level explanation of conditioning spikes/asymptotes.
7. Build `solver-convergence/` using controlled `rtol × max_step` sweeps plus an independent `atol` sensitivity study.
8. Stop verification infrastructure work once those three studies are satisfactory.
9. Begin the reduced-belt transient-term inventory.
10. Build coherent belt reductions from the resulting evidence.
11. Add targeted hybrid-regime studies only where remaining scientific questions require them.
12. Draft the final Chapter 4 structure only after these results stabilize.
