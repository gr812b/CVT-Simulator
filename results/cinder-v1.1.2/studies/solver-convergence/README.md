# Solver convergence

This study asks whether the **complete hybrid CINDER trajectory** converges as
LSODA numerical controls are tightened.

It loads only:

```text
../../defaults/baja_reference_simulation_case.json
```

and changes only the integrator settings recorded in `study.json`; the comparison grid is a study-local postprocessing choice. It does
not import setup helpers from another study or copy a `cvtModel` source tree.

The full paper-facing sweep evaluates:

\[
r_{\rm tol}
=
10^{-2},3\times10^{-3},10^{-3},3\times10^{-4},
10^{-4},3\times10^{-5},10^{-5},3\times10^{-6}
\]

against

\[
\Delta t_{\max}=100,50,20,10,5\ {\rm ms}
\]

with `atol = 1e-3 * rtol`, plus an independent seven-level absolute-tolerance
sweep.

Each run is compared with a tighter numerical reference using:

- all five CVT state trajectories;
- normalized RMS / maximum / final-state errors;
- transition count;
- exact transition signature;
- corresponding event-time errors;
- regime-history mismatch fraction;
- pure hybrid-integration wall time;
- native solver-point count as a transparent cost proxy.

The figures include the accuracy heatmap, hybrid-stability map, event-time
heatmap, cost curves, absolute-tolerance sensitivity, and loose/canonical/tight
trajectory overlays.

This study alone keeps a local `work/cache/` because the 40+ independent
integrations are expensive. That cache contains only outputs of this study and
can be deleted with `--fresh`.

Run from `results/cinder-v1.1.2`:

```powershell
python .\studies\solver-convergence\run.py
```

Quick machinery preview:

```powershell
python .\studies\solver-convergence\run.py --quick
```

Delete this study's cache and rerun:

```powershell
python .\studies\solver-convergence\run.py --fresh
```

<!-- solver-convergence finalization companions v1 -->
## Publication polish and optional dense explorer

The formal revision-4 numerical sweep is intentionally left unchanged.

Paper-facing figures can be regenerated from the frozen artifacts without
rerunning CINDER:

```powershell
python .\studies\solver-convergence\publication_plots.py
```

A separate exploratory dense sweep is available for high-resolution heatmaps,
contours, breakdown-boundary exploration, and high-density cost plots. It is
**never called by `run.py`** and writes only beneath `artifacts/dense-overnight/`:

```powershell
python .\studies\solver-convergence\overnight_dense.py --plan-only
python .\studies\solver-convergence\overnight_dense.py
```

The dense explorer is supplementary/exploratory and does not replace the frozen
formal verification dataset.

