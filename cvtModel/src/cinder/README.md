ODE state
    ↓
DynamicsSnapshot
    ↓
build_state_fixed_equations(snapshot)
    → state-fixed mechanics cached for the full RHS evaluation


DynamicsSnapshot + trial λp, λs
    ↓
TrialEquationContext
    ↓
closure-row builders
    ↓
8 affine closure rows
    ↓
TrialClosureSystem
    ↓
A z = b
    ↓
TrialClosureResult

Canonical closure basis:

    [ω̈_p, ω̈_s, v̇_b, s̈, τ_p, τ_s, N_p, N_s]

The normal-resultant contact rows are intentionally not yet assembled in the
current row builders. The generic closure layer already requires all eight
rows; no six-row compatibility projection is retained.
