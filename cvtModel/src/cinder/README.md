ODE state
    ↓
DynamicsSnapshot
    ↓
build_state_fixed_equations(snapshot)
    → rows 2–5, cached for the full RHS evaluation



DynamicsSnapshot + trial λp, λs
    ↓
TrialEquationContext
    ↓
build_shift_equation(context)          → row 1
build_wrap_endpoint_equation(context)  → row 6



rows 1–6
    ↓
TrialSixBySixSystem
    ↓
A z = b
    ↓
TrialSixBySixResult