# Ballew 2015 model-to-model benchmark

This study reconstructs the five-second simulated ATV/CVT acceleration case from
Ballew (2015) and compares it with CINDER 1.1.2.

It is the complete, maintained home of the benchmark. Everything required to
understand and re-run the comparison belongs here: source provenance,
digitization provenance, deterministic reference-data preparation, reconstruction
assumptions, benchmark-specific CINDER extension objects, numerical-robustness
checks, and fresh generated artifacts.

The `publication_inputs/` directory retains compact, hash-verified outputs of
the five CINDER 1.1.2 executions used for the final figures and B1 refinement.
The full fresh exports are generated under `artifacts/`. Their input snapshots,
output hashes and exact event records accompany the delivery evidence archive.

This is a **model-to-model comparison**, not experimental validation. Figure 41
and Figure 45 are outputs of Ballew's discretized-belt simulation. No CINDER
physical parameter or controller gain is fitted to those traces.

## Comparison protocols

The study retains the two complementary comparisons from the original Ballew
work.

### 1. Force replay

The digitized Figure 45 primary axial-force history is imposed on CINDER. CINDER
primary speed, secondary speed, and derived speed ratio are then compared with
Ballew Figure 41.

This isolates the plant response: given approximately the same primary clamp
history, do the two models produce the same macroscopic shift trajectory?

### 2. Reconstructed closed loop

Ballew publishes a 2500 rpm primary-speed objective and controller gains
`Kff = 1.2`, `Kp = 5`, `Ki = 75`, but not a complete executable controller
equation. The source-constrained reconstruction documented in
`provenance/RECONSTRUCTION.md` is applied around unchanged CINDER. Figure 45 is
then an **output reference**, never an input to the controller.

`analysis/run_controller_reconstruction.py` separately audits the controller sign and
error-unit interpretation against the digitized Ballew traces. Diagnostic fitted
gains reported by that audit are never fed back into the benchmark.

## Study layout

```text
ballew-2015/
├── README.md
├── study.json
├── verify_study.py
├── run.py
├── analysis/run_controller_reconstruction.py
├── analysis/run_convergence.py
├── exploration/run_stability_sweep.py
│
├── infrastructure/benchmark/
│   ├── constants.py        # published values + explicit reconstructed constants
│   ├── belt.py             # A4 equivalent-belt/geometry bridge
│   ├── actuation.py        # constant and tabulated axial-force extensions
│   ├── controller.py       # A11 PI host/state/force-law reconstruction
│   ├── case.py             # CINDER assembly, boundaries, inertias, initial state
│   ├── simulation.py       # high-level CINDER execution and dense sampling
│   ├── reference.py        # reference integrity/loading helpers
│   └── metrics.py          # comparison metrics/plots
│
├── reference/
│   ├── source/
│   │   └── Ballew_2015_thesis.pdf
│   ├── digitization/
│   │   ├── input_rpm.csv
│   │   ├── output_rpm.csv
│   │   ├── axial_force.csv
│   │   ├── rpms_ballew.json
│   │   └── axial_force_ballew.json
│   ├── prepare_reference_data.py
│   ├── figure_41_input_rpm.csv
│   ├── figure_41_output_rpm.csv
│   └── figure_45_primary_force.csv
│
├── provenance/
│   ├── README.md
│   ├── RECONSTRUCTION.md
│   ├── CINDER_FIXES.md
│   ├── CINDER_1_1_2_UPDATE.md
│   └── NUMERICAL_STABILITY.md
│
└── artifacts/              # generated fresh; not source material
```

The five files under `reference/digitization/` are immutable source provenance.
The three benchmark-ready CSVs one directory above them are reproducibly derived
by `prepare_reference_data.py`.

## Reference-data preparation

From the study directory:

```powershell
python reference/prepare_reference_data.py
python reference/prepare_reference_data.py --check
```

Preparation is intentionally minimal:

1. add explicit headers to the raw WebPlotDigitizer CSV exports;
2. retain the two Figure 41 traces on their own native digitized time grids;
3. average exact duplicate Figure 45 time coordinates;
4. prepend a `t=0` Figure 45 value by holding the first visible force point
   backward over the short unsupported initial interval.

There is no smoothing, filtering, resampling, curve fitting, or controller
reconstruction in this step. See `reference/README.md` and Reconstruction A6/A7.

## Why this is a Python study instead of a serialized baseline override

PR #476's ordinary results studies derive from a frozen serialized simulation
case. Ballew cannot be represented honestly as only a JSON override because the
benchmark requires two legitimate CINDER 1.1.2 Python extension points:

- a tabulated primary axial-force law for force replay;
- a PI-controlled primary force law with an integrated host state for the
  closed-loop reconstruction.

The study therefore keeps those **benchmark-specific extension objects local**
while using the published CINDER package for the mechanics. It:

- verifies the release environment;
- never adds the repository's live `cvtModel/src` tree to `sys.path`;
- validates the assembled CVT through `cinder.contracts.validate_assembly`;
- executes through `ComposedCVTHybridSystem.run`;
- projects the standard result through `cinder.contracts.project_simulation_result`;
- writes the complete resolved published/reconstructed parameter document and
  reference hashes with each fresh run.

This is the study-level exception to the ordinary serialized-default pattern;
it should be treated explicitly rather than pretending the custom objects are
built-in JSON contracts.

## Re-running the benchmark

First create/activate the frozen CINDER 1.1.2 results environment described by
`results/cinder-v1.1.2/README.md`.

From `results/cinder-v1.1.2/`:

```powershell
python verify_environment.py
python studies/ballew-2015/verify_study.py
python studies/ballew-2015/run.py
```

Optional audits/studies:

```powershell
# Source-only audit of the incompletely published PI controller equation.
python studies/ballew-2015/analysis/run_controller_reconstruction.py

# Four-point refinement check around the nominal closed-loop settings.
python studies/ballew-2015/analysis/run_convergence.py

# Broader numerical operating-envelope study.
python studies/ballew-2015/exploration/run_stability_sweep.py --preset smoke
python studies/ballew-2015/exploration/run_stability_sweep.py --preset quick
```

All generated files are written beneath `artifacts/`. Re-running the canonical
comparison clears only the canonical protocol outputs unless `--keep-artifacts`
is supplied.

## Reconstruction documentation

`provenance/RECONSTRUCTION.md` is normative for the source-to-CINDER bridge. It
separates values published by Ballew from quantities that must be reconstructed
because the two models use different coordinates, inertia ownership, friction
normalizations, or controller representations.

The main bridges are:

- inertia ownership and vehicle-load reconstruction;
- exact initial state from the published shaft speeds;
- Figure 39 equivalent belt-core/cord-line geometry mapping;
- zero moving-sheave masses to represent Ballew's algebraic clamp balance;
- Figure 41/45 digitization handling;
- friction-capacity translation between Ballew's node convention and CINDER's
  reduced pulley-contact convention;
- the incompletely published PI + feed-forward controller reconstruction.

## CINDER implementation corrections exposed by this benchmark

The Ballew reconstruction also exposed several general CINDER implementation
issues around piecewise-smooth geometry and hybrid admissibility. They were
fixed in CINDER itself before v1.0.0 and are **not benchmark-local patches**.
`provenance/CINDER_FIXES.md` records why those corrections are physically and
mathematically necessary so the benchmark remains auditable without carrying an
alternate copy of CINDER mechanics.

## Final manuscript figures and B1 refinement (25 September 2026)

From the repository root, with the frozen environment prepared:

```bash
# Fast reproduction from committed, verified outputs; no simulation rerun.
results/cinder-v1.1.2/.venv/bin/python \
  results/cinder-v1.1.2/studies/ballew-2015/run.py --plot-only \
  --figure-dir docs/CVT_Module_Formulation/figures/results/ballew

# Full numerical reproduction: both protocols + three additional refinements.
results/cinder-v1.1.2/.venv/bin/python \
  results/cinder-v1.1.2/studies/ballew-2015/run.py --with-refinement \
  --figure-dir docs/CVT_Module_Formulation/figures/results/ballew
```

For the final first-figure axis revision, add `--figure protocol-comparison`
to the plot-only command. Both secondary-speed panels use 0–1400 rpm. This
regenerates only `protocol_comparison.pdf/png`; the internal-response files
are preserved with their original generator attribution in the manifest.

The final plotter is `analysis/publication_plots.py`. It draws segmented native
shaft states and unsmoothed report channels, preserving duplicate event times.
`analysis/publication_evidence.py` checks the executed source/output hashes,
recomputes native-reference errors, checks both endpoints of every segment,
reintegrates slip loss, and compares all four closed-loop traces on a common
dense-output grid. It then selects arrays into `publication_inputs/` without
resampling them. The selector retains the complete common-grid state and
controller integral for refinement reanalysis.

The original production used the canonical `run.py --no-plots`, followed by
`analysis/run_convergence.py --reuse-nominal` and the evidence selector. The
new `--with-refinement` flag orchestrates those same operations. Executed source
snapshots identify that earlier invocation exactly; adding publication and CLI
orchestration did not change the model, reconstruction or integration settings.

All four refinement cases retain the same ordered 1415 event records after
excluding only kinetic-slip direction updates. The latter counts are
320/320/307/6; raw event totals are therefore not identical. Maximum matched
non-direction event-time shift is 1.673 microseconds. Maximum RMS differences
from the nominal trace are 0.03203 rpm in primary speed and 0.1604 N in clamp.
A fixed-time shift-speed comparison can cross opposite capture sides; the audit
retains that 6.41 m/s difference instead of hiding it. See Appendix D.5 and
`provenance/NUMERICAL_STABILITY.md` for interpretation.

The older recovered benchmark archive identifies CINDER 1.0.0, and the August
refinement predates 1.1.2. Neither is used as numerical evidence for this unit.
The fresh canonical errors match the retained 1.1.2 interpretation memo.

`plot_provenance.json` records figure/input hashes and canvas dimensions.
Matplotlib PDF/PNG metadata are fixed for byte-identical exports in the recorded
environment. The compact execution manifests refer to the full raw outputs,
whereas `publication_inputs.json` hashes the selected committed arrays.
