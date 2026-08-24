# 45 s mechanical-energy audit

Generated from the PR #471 mechanics + current `develop` semantic merge with:

```bash
PYTHONPATH=src MPLBACKEND=Agg python tools/audit_energy_balance.py \
  --output-dir validation/energy_audit \
  --rtol 1e-4 --atol 1e-7 --max-step 0.02 --audit-step 0.02
```

Final audit from this package:

- primary boundary work: +233.227806 kJ
- secondary/road boundary work: -155.068029 kJ
- net external work: +78.159777 kJ
- kinetic-slip dissipation: 2.161453 kJ
- discrete capture/stop dissipation: 0.057932958 J
- stored mechanical-energy increase: 75.998521 kJ
- residual: -0.255713 J
- residual / net external work: 0.000327%
- residual / primary input work: 0.000110%

`transition_energy_audit.csv` records every momentum projection. All discrete
capture/impact losses are non-negative and the finite-speed stop/capture maps
use the generalized mass-metric momentum projection.

The residual is sub-joule on a ~78 kJ net-work balance and is not localized to
an unmodelled transition loss.
