# 45 s mechanical-energy audit

Generated with:

```bash
PYTHONPATH=src MPLBACKEND=Agg python tools/audit_energy_balance.py \
  --output-dir validation/energy_audit \
  --rtol 1e-4 --atol 1e-7 --max-step 0.02 --audit-step 0.02
```

Final audit from this package:

- primary boundary work: +233.234141 kJ
- secondary/road boundary work: -155.054621 kJ
- net external work: +78.179520 kJ
- kinetic-slip dissipation: 2.161453 kJ
- discrete capture/stop dissipation: 0.057928820 J
- stored mechanical-energy increase: 75.998012 kJ
- residual: 19.996850 J
- residual / net external work: 0.025578%
- residual / primary input work: 0.008573%

`transition_energy_audit.csv` records every momentum projection.  All discrete
losses are non-negative.  The largest event momentum residual is about
`2.84e-14`; the upper-stop event now dissipates a small positive amount instead
of creating energy.

The remaining global residual is a continuous ODE/quadrature error distributed
over the 45 s run rather than a transition-localized energy jump.
