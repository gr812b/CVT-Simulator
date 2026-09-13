# Temporary missing-coverage exploration

This overlay adds **one separate diagnostic script**. It does not modify `run.py`, `study.json`, the production CINDER package, or the canonical invariant-study PASS/REVIEW logic.

## Purpose

The v2 operating-domain audit covered 23 of 25 requested classes. The two unresolved classes were:

- `both_slip_quadrant_mp`: primary relative motion negative, secondary relative motion positive;
- `secondary_slip_both_directions`: specifically the missing positive-secondary-slip mixed branch (`primary_stick_secondary_slip` with positive secondary relative speed).

The prior deterministic search taught us something useful but did not settle reachability. In particular, its contact IC constructor used the **same slip-speed magnitude at both contacts** for both-slip cases, and its edge fallback did not explore very low belt transport speeds. The temporary script explicitly removes those restrictions before we make any change to the canonical checker.

## What the script does

`explore_missing_coverage.py` uses the same frozen v1.1.2 plant, fixed-shaft boundary class, inspection code, hard invariant checks, and hybrid integrator as the main study. It adds no contact physics.

Each candidate is evaluated two ways:

1. **Forced requested branch evaluation.** The production branch solver is explicitly asked to solve the missing topology at the prescribed state. This reveals whether the branch equations themselves can satisfy static traction, belt tension, local distributed normal loading, resultant normals, mechanism contacts, closure residuals, and contact kinematics.
2. **Normal production classification.** The same state is passed through CINDER's initial-regime classifier. This shows whether production would actually select the requested branch rather than relax to another topology.

Only if both of those pass does the script run a short hybrid continuation and audit all sampled states plus exact post-transition successor states. A candidate marked `full_dynamic_pass=True` is therefore strong evidence that the missing class is genuinely reachable without changing the model or weakening an invariant.

## New exploratory degrees of freedom

The search deliberately varies things the v2 coverage search did not vary independently:

- primary and secondary slip magnitudes **independently** for the `mp` quadrant;
- belt transport speed down to near zero and through both signs;
- shift position across nearly the full engaged domain;
- nonzero shift speed, with target relative speeds reconstructed using CINDER's own representative-contact kinematics so secondary helix motion is included;
- primary and secondary boundary torque;
- primary and secondary equivalent boundary inertia.

The search begins in moderate ranges and then broadens. The broad stage is exploratory only; if a candidate is found only under extreme boundary values, inspect that candidate before promoting it into the canonical coverage study.

## Run

From `results/cinder-v1.1.2/studies/mechanical-invariants/`:

```bash
python explore_missing_coverage.py
```

Default budget is 12,000 candidates total, split across the two missing targets. To search harder:

```bash
python explore_missing_coverage.py --budget 20000
```

To isolate one target:

```bash
python explore_missing_coverage.py --target both_slip_mp --budget 10000
python explore_missing_coverage.py --target secondary_slip_plus --budget 10000
```

## Outputs

Nothing in the normal `artifacts/` root is overwritten. The temporary results go to:

`artifacts/missing-coverage-exploration/`

The most useful files are:

- `summary.md` / `summary.json` — whether each missing class was found and at what level;
- `best_candidates.csv` — the best/closest states even if no class is found;
- `attempts.csv` — complete candidate log;
- `01_both_slip_mp_feasibility.png` — minimum belt tension vs. minimum primary distributed normal loading;
- `02_secondary_slip_plus_feasibility.png` — primary static traction margin vs. minimum primary distributed normal loading;
- `03_classifier_outcomes.png` — which topology the production classifier selected.

## Interpretation hierarchy

There are three useful outcomes, in increasing strength:

1. **No forced-branch pass.** We still have no evidence that the requested retained topology is physically admissible in the searched domain. The closest margins tell us which inequality prevents it.
2. **Forced branch passes, classifier does not select it.** The branch equations can be mechanically admissible, but the production classification policy chooses another topology. That is a classifier/complementarity question, not a belt-field failure.
3. **`full_dynamic_pass=True`.** The production classifier selects the missing topology, its exact initial state passes the same hard invariant checks as the canonical study, and a short hybrid continuation plus exact successor-state audits remain healthy. This is the candidate we would then fold cleanly into the canonical checker.

Do **not** edit the main invariant checker just because this exploratory script finds something. First inspect the returned state and boundary conditions; then we can decide the smallest principled canonical change.
