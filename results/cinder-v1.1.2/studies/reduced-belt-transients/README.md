# Reduced-belt transient mechanics — phase-aware exploration

## Question

Within CINDER's dynamically closed reduced whole-belt model, **which terms that survive in the final solved belt equations are active in ordinary operation, what operating conditions activate them, and which effects deserve a targeted follow-up before any coherent reduction is attempted?**

The study remains discovery-first. It does not change the CVT governing equations, contact law, actuator mechanics, closure, or hybrid state machine, and it contains no belt-ablation switch.

## Final equations being studied

Whole-belt transport:

\[
m_b\dot v_b+\tau_p/r_{p,\mathrm{eff}}+\tau_s/r_{s,\mathrm{eff}}=0.
\]

Independent tension-loop compatibility:

\[
R_{\ddot s}+R_{\dot s^2}+R_{\dot v_b}+R_{\dot s v_b}+R_N=0.
\]

Only these surviving terms are scientific study channels. Terms that cancel exactly before these final equations are reached are not resurrected as trajectory diagnostics.

For the four transient tension-loop terms the output now records both the term itself and the exact multiplicative split

\[
R_i=K_iD_i,
\]

where \(D_i\) is the kinematic driver and \(K_i\) is the operating-point response coefficient. This distinguishes a term that is small only because its driver happened to be small from one that is intrinsically weak over the active ratio/contact range.

## Stage A — broad natural trajectories

The original four broad cases remain:

1. flat launch and natural upshift;
2. 8 degree spatial grade step;
3. 18 degree spatial grade step;
4. 28 degree spatial grade step.

They provide launch, contact-transition, free upshift, load arrest, and natural backshift coverage without tuning the CVT to excite one preferred term.

The analysis no longer lets the common initial engagement event dominate the headline result. Every case is split using the actual hybrid regime into contact-transition/slip, low-ratio stick, free stick, free-stick upshift, free-stick backshift, and upper-stop stick when present. The free-stick data are additionally sliced by physical shift fraction, contact-demand fraction \(\max(|\lambda_p|,|\lambda_s|)/\mu_s\), and free-stick-only upper-quartile kinematic excitation.

## Stage B — controlled disturbance search

The broad run showed that the radial shift-acceleration term can be quiet in smooth operation but wake up sharply at an external load discontinuity. Stage B therefore separates **disturbance timescale** from **disturbance magnitude** using a smooth time-programmed road-grade boundary while leaving the CVT plant unchanged.

All controlled cases are identical until \(t=1.50\) s, after the baseline CVT has reached free engaged motion.

Timescale axis, fixed 18 degree target:

- ideal step;
- 50 ms smooth rise;
- 200 ms smooth rise;
- 800 ms smooth rise.

Magnitude axis, fixed 200 ms smooth rise:

- 8 degrees;
- 18 degrees;
- 28 degrees.

The smooth transitions use a cubic smoothstep, so both grade and its first time derivative join continuously at the endpoints. This avoids interpreting a staircase approximation as physical belt dynamics.

## Broad secondary searches from the same trajectories

No additional simulation is needed for several useful questions. The postprocessor also searches:

- shift/ratio dependence in four fixed shift-fraction bands;
- contact-demand dependence in fixed fractions of static traction capacity;
- upshift versus backshift sign/direction;
- whether each small term is limited by its driver or by its response coefficient;
- where whole-belt transport inertia is largest even when it remains small relative to the opposing pulley reactions;
- peak context for every final-equation term, including ratio, grade, contact demand, shift acceleration, and belt acceleration.

These are orientation outputs, not deletion criteria.

## Running

Run everything:

```powershell
python studies/reduced-belt-transients/run.py
```

Only the broad natural cases:

```powershell
python studies/reduced-belt-transients/run.py --stage broad
```

Only the controlled smooth-load cases:

```powershell
python studies/reduced-belt-transients/run.py --stage controlled
```

Pure algebra/protocol tests only:

```powershell
python studies/reduced-belt-transients/run.py --tests-only
```

## Important outputs

Each case writes the raw `belt_terms.csv`, a phase-aware `summary.json`, `phase_summary.csv`, the original final-equation plots, operating context, driver maps, and response-coefficient-versus-shift plots.

The study root additionally writes:

- `exploration_summary.csv` — overall and free-stick-only cross-case summaries;
- `term_envelope.csv` — broad free-stick envelope and peak context for each term;
- `activity_by_shift_fraction.csv` — ratio dependence;
- `activity_by_contact_demand.csv` — contact-demand dependence;
- `response_coefficients_by_shift.csv` — operating-point coefficient variation;
- `controlled_load_summary.csv` — common-window metrics for the smooth load study;
- `cross_case_free_stick_activity.png` — broad cases without engagement domination;
- `controlled_timescale_R_sddot.png` — fixed-magnitude rise-time result;
- `controlled_severity_R_sddot.png` — fixed-rise-time magnitude result.

## Decision gate

Do not infer a reduction solely from a small force/activity share. The study first identifies whether a term is persistent, event-only, driver-limited, coefficient-limited, ratio-dependent, contact-dependent, or structurally dynamic. Only after these results are interpreted should a coherent reduced formulation be derived and compared against the full trajectory and invariant/energy checks.
