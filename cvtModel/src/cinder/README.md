Continuous ODE state
    ↓
`cinder.integration.CVTDynamicState`
    ↓
DynamicsSnapshot
    ↓
`build_state_fixed_equations(snapshot)`
    → five lambda-independent mechanics rows cached for the full RHS evaluation


DynamicsSnapshot + trial signed λp, λs
    ↓
TrialEquationContext
    ↓
three lambda-dependent closure rows
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

    1. primary shaft rotation                    state-fixed
    2. whole-belt tangential momentum            state-fixed
    3. secondary shaft rotation                  state-fixed
    4. primary physical axial balance            state-fixed
    5. secondary physical axial balance          state-fixed
    6. primary integrated traction resultant     lambda-dependent
    7. secondary integrated traction resultant   lambda-dependent
    8. closed tension-loop compatibility          lambda-dependent

`ContactTractionUtilization` stores the signed effective traction ratios:

    λ_j = Q_j / N_j = τ_j / (r_tau,j N_j).

It is not a commanded percentage. A stick solve finds the static traction
requirement. `ContactTractionLaw` separately decides whether that requirement
lies within physical signed static limits. In a selected slip branch, the law
provides the kinetic lambda magnitude and the stored slip direction supplies
its sign.

`LambdaSearchBounds` is strictly numerical. It intentionally must not be used
as the physical traction limit, because a required stick solution outside
physical capacity is useful information for selecting a slip branch.
