# Mechanical invariants

This study asks whether the **accepted CINDER trajectory itself** satisfies the
local mechanical equations and admissibility conditions of the formulation.

It loads only:

```text
../../defaults/baja_reference_simulation_case.json
```

and applies the numerical/time-span overrides recorded in `study.json`. There
is no shared study framework and no copied `cvtModel` source tree.

The audit reconstructs accepted states directly with the installed
`cinder-cvt==1.1.2` mechanics and checks:

- engaged belt-loop geometry closure;
- all eight production engaged-closure equations, in both raw and row-scaled residual form;
- 8×8 matrix rank;
- stick relative-speed drift and acceleration compatibility;
- static-friction capacity margins;
- kinetic-slip direction and dissipative contact-pair power;
- primary and secondary normal-resultant non-negativity;
- deadzone lower stop, engaged low-ratio seat, and upper-stop reactions;
- active fixed-shift constraints;
- deadzone belt-secondary lock;
- exact post-transition states.

Run from `results/cinder-v1.1.2`:

```powershell
python .\studies\mechanical-invariants\run.py
```

The paper-facing result is `artifacts/summary.md` plus the five PNG diagnostics.
The detailed CSVs remain available to audit any localized anomaly.
