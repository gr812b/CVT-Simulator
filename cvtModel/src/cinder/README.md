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

Current fixed-λ row order:

    1. primary shaft rotation
    2. whole-belt tangential momentum
    3. secondary shaft rotation
    4. primary physical axial balance
    5. secondary physical axial balance, mapped through x_s(s)
    6. primary integrated traction resultant
    7. secondary integrated traction resultant
    8. closed tension-loop compatibility

The snapshot resolves primary, secondary, and representative belt axial
translation inertias individually. The current physical pulley axial rows use
the primary and secondary entries directly. The belt axial entry remains
explicit for the later derivation of its own distributed/representative axial
force treatment; it is not silently absorbed into either pulley-local row.
