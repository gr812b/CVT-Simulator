# CINDER Results Working Ledger
**Status:** active / exploratory  
**Rule:** Record the question first. Add findings only after a reproducible study exists. Nothing here is a frozen manuscript claim.

## Current release work

| Item | Status | Next action |
|---|---|---|
| Final CINDER release for results | OPEN | Confirm exact version/tag after transition audit |
| New release-scoped results directory | TODO | Create after mechanics are confirmed |
| Preserve `cinder-v1.0.0` | LOCKED | Never silently migrate |
| Ballew port | TODO | Port, rerun, compare to 1.0.0 |
| Launch/hill port | TODO | Port and verify |
| Correctness/energy study | TODO | Promote current audit to release-scoped study |

## Scientific ledger

| Question | Study / evidence | Current state | Next action |
|---|---|---|---|
| Does global mechanical energy close? | Current energy audit | Strong preliminary result; sub-joule residual on ~78 kJ net work in prior run | Re-run on final release; add normalized diagnostics |
| Are impact/capture transitions momentum-consistent? | `cvt_impact`, event metadata, smoke tests | Implemented; residuals and non-increasing KE checked | Include in formal correctness study |
| Are conclusions solver-independent? | Ballew convergence + stability sweep | Existing methodology | Port and extend to normal + difficult hybrid cases |
| Does CINDER match Ballew macroscopic dynamics? | Closed-loop reconstruction | Prior ~3–5% RPM/ratio RMSE | Re-run final release |
| Does CINDER match Ballew clamp→shift plant response? | Force replay | Prior substantial disagreement | Re-run and investigate physically |
| What is the best intuitive reference transient? | Launch / hill infrastructure | Candidate exists | Design final mechanism-first plot sequence |
| Does flyweight dynamic inertia matter? | Dynamic actuator ablation | Infrastructure exists | Port and rerun |
| Does secondary helix inertia matter at Baja scale? | Dynamic actuator ablation | Infrastructure exists | Port and quantify |
| When does helix inertia become important? | Inertia × torque scaling | Infrastructure exists | Port and interpret threshold map |
| Which reduced-belt transient terms matter? | New term audit | OPEN | Inventory every retained term |
| Can some belt terms be removed safely? | New coherent ablations | OPEN | Only after term audit |
| What hybrid transitions occur in normal operation? | Regime trace studies | OPEN | Catalog baseline launch/load case |
| Which hybrid transitions matter only under stress? | Targeted scenarios | OPEN | Build after baseline |
| Are current novelty claims already in literature? | Literature matrix | OPEN | Maintain continuously |

## Current interpretation boundaries

- Energy/convergence = **verification**, not experimental validation.
- Ballew = **model-to-model comparison**, not direct validation.
- Closed-loop Ballew agreement does not imply identical plant mechanics.
- A small dynamic-inertia effect can still justify a quasi-static reduction.
- Retaining a term is not automatically novel; compare literature before claiming novelty.
- Do not force a study to produce a “positive” result. Negligibility boundaries are useful findings.
- Hybrid capability should be presented through physical questions, not merely a list of modes.

## Open mechanics issue before new results

### Section 3.6 transition compatibility / changing-radius velocity terms
Question:
Does the generalized impact/capture map include every retained kinetic velocity associated with a topology-dependent \(r_j'(s)\dot s\), especially belt radial motion on changing-radius wraps?

Status:
**REAL, NARROW IMPLEMENTATION GAP FOUND — FIX BEFORE RESULTS FREEZE.**

Finding:
- Smooth Section 3.4 / CINDER equations already retain the changing-radius wrap terms.
- Smooth sticking compatibility already contains \(-r_j'\dot s\,\omega_j\).
- Section 3.6's mass-metric/KKT architecture is correct.
- The current impact kinetic map includes full-belt transport \(v_b\), but omits the radial wrap modes \(\dot r_p=r_p'\dot s\) and \(\dot r_s=r_s'\dot s\).

Minimal fix:
- add primary/secondary wrap radial velocity rows to the existing physical-velocity map;
- weight them by \(m_{\mathrm{wrap},j}=\rho_bA_b r_{j,\mathrm{cm}}\phi_j\);
- keep the existing global belt transport row;
- rerun transition tests and the full time-resolved energy audit.

Preliminary Baja scale:
- omitted generalized radial wrap inertia ~0.50–0.84 kg across engaged shift;
- literal sheave translational contribution ~1.43–1.85 kg;
- therefore the omitted term is ~35–45% of the literal sheave translational contribution and should not be assumed negligible.

Acceptance rule:
Do not freeze the next CINDER results release until the corrected projector passes impact tests and the energy audit remains mechanically closed.
