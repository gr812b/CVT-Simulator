# Mechanical-energy consistency

This is the release-level energy-consistency study for **CINDER 1.1.2**.

## Question

Within the mechanics explicitly retained by CINDER 1.1.2, does the mechanical
energy balance close across both continuous contact regimes and discrete hybrid
transitions? Does the remaining numerical residual behave consistently under
quadrature and ODE refinement?

The audited identity is

```text
external shaft work
    =
change in stored mechanical energy
  + kinetic-slip dissipation
  + discrete impact/capture dissipation
  + numerical/model residual.
```

Stored mechanical energy includes the kinetic modes retained by the released
CINDER transition metric plus conservative axial- and torsional-spring energy.

This study is intentionally **neutral with respect to the source of any
residual**. It does not search for, subtract, or fit a particular missing power
term. Every modeled energy channel is accounted for using the released mechanics
and the unexplained remainder is reported directly.

## Baseline

The study derives from

```text
../../defaults/baja/simulation_case.json
```

and changes **no mechanical parameter**. The canonical audit extends the flat
reference launch to 10 s and uses tighter solver settings only to resolve the
energy identity:

```text
nominal: rtol=3e-5, atol=3e-8, max_step=0.01 s
tight:   rtol=9e-6, atol=9e-9, max_step=0.005 s
```

The nominal trajectory is audited on four independent dense-output quadrature
grids:

```text
5.000 ms
2.500 ms
1.250 ms
0.625 ms
```

Short hybrid segments receive at least 12 intervals regardless of their
duration, so millisecond-scale contact events are not represented only by their
endpoints.

## What is checked

The study reports five complementary pieces of evidence.

1. **Global work-energy balance.** Boundary work is compared with stored-energy
   change, kinetic-slip dissipation, and discrete impact/capture dissipation.
2. **Continuous-regime localization.** Each uninterrupted hybrid segment is
   audited separately using exact segment endpoint energies.
3. **Quadrature refinement.** The same nominal trajectory is integrated on
   progressively finer audit grids, with a second-order Richardson estimate
   reported for the continuous residual.
4. **Discrete-event closure.** Exact pre/post stored-energy drops are compared
   with CINDER's recorded impact/capture loss and projection residuals.
5. **Solver refinement.** The complete trajectory is repeated with tighter ODE
   tolerances and the final physical state and energy balance are compared.

The runner also measures signed `lambda*N*v_rel` work at contacts declared
sticking. Exact sticking has `v_rel=0`; therefore this is reported only as a
**numerical velocity-level invariant-drift diagnostic**. It is not added to the
physical dissipation budget and is not used to make the raw residual look
smaller.

## Why the study uses a few release-internal inspection hooks

The simulation itself is built and validated from CINDER's public serialized
simulation-case contract and runs only the installed `cinder-cvt==1.1.2`
distribution.

Total stored mechanical energy and arbitrary-time contact power are not exposed
as one serialized public result today. The analysis therefore reads the exact
release's kinetic topology metric and solved contact state through release-local
Python inspection hooks. These calls do not modify the equations or states. The
release directory freezes the package version specifically so this inspection is
reproducible.

No repository `cvtModel/src` directory, launch tool, alternate mechanics copy, or
local patch is imported by the study.

## Run

First create and activate the release environment from
`results/cinder-v1.1.2/`, then run:

```powershell
python studies/energy-consistency/verify_study.py
python studies/energy-consistency/run.py
```

A shorter smoke run is available while editing the study:

```powershell
python studies/energy-consistency/run.py --quick
```

The canonical result is the default run, not `--quick`.

## Generated artifacts

`run.py` recreates `artifacts/` and writes:

- `resolved_simulation_case_nominal.json` — exact nominal executed input;
- `resolved_simulation_case_tight.json` — exact refined executed input;
- `summary.json` — machine-readable headline results and acceptance checks;
- `summary.md` — reader-facing result summary;
- `energy_trace_finest.csv` — cumulative energy identity on the finest nominal
  audit grid;
- `energy_trace_tight_finest.csv` — same for the refined ODE trajectory;
- `continuous_segment_balance.csv` — per-regime residuals on every quadrature
  grid;
- `quadrature_convergence.csv` — global continuous residual versus audit step;
- `event_energy_balance.csv` — exact hybrid event energy and projection checks;
- `energy_balance_cumulative.png`;
- `energy_channels.png`;
- `energy_balance_residual.png`;
- `quadrature_convergence.png`;
- `continuous_segment_residuals.png`;
- `event_losses.png`.

Generated numerical results are deliberately absent from the clean study until
the runner is executed against the published wheel.

## Interpretation boundary

A passing result shows that the equations **retained by CINDER 1.1.2** exchange
and store energy consistently to the stated numerical resolution. It is not an
experimental validation and it does not show that physics intentionally omitted
from the model is negligible. Belt longitudinal elasticity, local seating and
creep, radial face friction, straight-span transverse path motion, rubber
hysteresis, and other higher-fidelity effects remain outside this accounting
unless they are explicitly represented by the release.

## Manuscript Section 4.2.2 publication path

The final figure is maintained in `analysis/publication_plots.py`; its numerical
checks are in `analysis/verification.py`. Canonical `run.py` invokes this path
after a complete run. From the repository root, using the isolated release
interpreter:

```bash
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/verify_environment.py
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/energy-consistency/verify_study.py
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/energy-consistency/run.py
```

For already verified outputs, restore the delivered `artifacts/` directory,
including `execution_provenance.json` and `execution_inputs/`, then use:

```bash
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/energy-consistency/run.py --plot-only
```

An optional `--publication-dir /absolute/output/path` writes the four publication
assets to a clean directory for byte-comparison. The default destination is
`docs/CVT_Module_Formulation/figures/results/verification/`, containing
`energy_balance.pdf`, `.png`, `_values.json`, and `_provenance.json`.
`--no-plots` generates the complete numerical evidence and execution record
without figures. `--quick` is a smoke run and cannot support the publication
figure; `--plot-only` rejects incomplete evidence.

The 23 September execution used the frozen installed CINDER wheel, Python
3.12.14, NumPy 2.5.2, SciPy 1.18.1 and Matplotlib 3.11.1. The complete observed
package set is pinned in `provenance/requirements-executed.txt`; see the release
README to construct the isolated environment. Do not import the newer live
simulator. Exact executed source/input bytes and all numeric output hashes are
in the portable execution record; `provenance/execution_2026-09-23.json` is its
committed copy. Figure regeneration checks those identities and the isolated
import before trusting the evidence. Merely matching a CSV filename is not
sufficient.

The export now retains both exact native event sides, with `segment_index` and
`sample_location`; equal timestamps must not be deduplicated. Capture loss is
added only on the outgoing side. The new `native_transitions.csv` and
`native_transitions_tight.csv` include all transitions, including those without
capture projections. `event_energy_balance_tight.csv` supplements the original
nominal capture table. No work quadrature spans a reset, and signed sticking
work remains a diagnostic, not dissipation. These are accounting/export changes;
case inputs, dynamics, solver settings, quadrature spacings and acceptance
limits are unchanged.

The fourth figure panel was not imposed by the handoff placeholder. A short-time
view is necessary because the ten-second residual curve compresses the interval
around the upper stop into an apparent jump. The detail retains each native
side and separates continuous integration from the energy update at capture.
See `provenance/SECTION_4_2_2.md` for the complete selection, numerical comparison
with the draft, limitations, and source locators.

The focused integrity regressions use the retained evidence and make in-memory
corruptions only (dropped incoming endpoint, unsigned residual, and capture loss
assigned to the incoming side):

```bash
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/energy-consistency/analysis/test_publication_integrity.py
```

They supplement the full data checks performed automatically by `--plot-only`;
they are not independent scientific validation.
