# CINDER 1.1.2 Results

This directory is the frozen Results workspace for the manuscript calculations
performed against **CINDER 1.1.2**.

```text
CINDER source tag: cinder-v1.1.2
mechanics commit:  7637a38b4fb9ec21dfb953c1c80a27ec5f389654
PyPI package:      cinder-cvt==1.1.2
Python:            3.12
NumPy:             2.5.2
SciPy:             1.18.1
Matplotlib:        3.11.1
```

The installed `cinder-cvt==1.1.2` wheel is the mechanics implementation. Do not
put the repository's live `cvtModel/src` tree on `PYTHONPATH` and do not upgrade
the pinned Results dependencies to reproduce this release.

## One public command

From repository root, use `results.py` for the maintained Results workflows:

```powershell
py -3.12 results/cinder-v1.1.2/results.py bootstrap
python results/cinder-v1.1.2/results.py verify
python results/cinder-v1.1.2/results.py --help
```

The detailed implementations live under `results_health/workflows/`; they are
kept separate for testing but are not separate user-facing entry points.

### Numerical run / health audit

```powershell
python results/cinder-v1.1.2/results.py run --mode correct
python results/cinder-v1.1.2/results.py run --mode check
python results/cinder-v1.1.2/results.py run --mode all
python results/cinder-v1.1.2/results.py run --mode all --dry-run
```

Generated run records go to `health_runs/` and are ignored by Git.

### Prepare accepted evidence

Preparation reuses completed numerical runs, rebuilds/checks compact publication
inputs, and can smoke-test exporters. It launches **zero CVT integrations**.

```powershell
python results/cinder-v1.1.2/results.py prepare `
  --from-run results/cinder-v1.1.2/health_runs/20260929T124106516965Z `
  --ballew-run results/cinder-v1.1.2/health_runs/20260929T165922834300Z `
  --fetch-lfs
```

The accepted localized preparation used for the current figure freeze is
`prep_20260929T205331850596Z`.

If retained evidence lives elsewhere, pass a small JSON file containing only
the needed overrides, for example:

```json
{
  "primary_screen": null,
  "solver_artifacts": "D:/CINDER-evidence/solver/evidence/artifacts",
  "closure_artifacts": "D:/CINDER-evidence/closure/evidence/reviewed"
}
```

### Reproduce manuscript figures

The figure workflow is deliberately non-integrating. It uses the explicitly
identified accepted numerical runs and retained solver/closure evidence, checks
the current TeX figure inventory, and writes candidates to ignored `figure_runs/`.

```powershell
python results/cinder-v1.1.2/results.py figures `
  --solver-retained C:\path\to\CINDER_4_2_3_Rebuilt_2026-09-25 `
  --closure-retained C:\path\to\CINDER_4_2_4_Rebuilt_2026-09-25 `
  --preflight-only
```

Then remove `--preflight-only` and provide a fresh `--output-dir`. The workflow
does not promote candidates into the manuscript directory automatically.

### Tests and study checks

```powershell
python results/cinder-v1.1.2/results.py test
python results/cinder-v1.1.2/results.py studies
python results/cinder-v1.1.2/results.py studies --manifests-only
```

## Reference model

The shared Baja Results reference model uses a zero-clearance bilateral/slotted
secondary helix. `defaults/baja/simulation_case.json` is the frozen public
solver input, `defaults/reference_model/` owns the executable Results
interpretation, and `defaults/verification/operating_cases.json` contains the
reusable verification operating cases.

Studies that construct independent hardware, such as the Ballew benchmark,
remain explicit and do not inherit the shared Baja assembly.

## What is committed vs generated

```text
results/cinder-v1.1.2/
├── README.md
├── results.py
├── bootstrap.py
├── verify_environment.py
├── requirements.txt
├── defaults/
├── studies/
├── results_health/
└── repo_tools/
```

Generated `.venv/`, `work/`, `artifacts/`, `health_runs/` and `figure_runs/`
directories are not source and are ignored by Git.

Large retained publication-input NPZ/JSON files under individual studies are
intentional evidence, not disposable scratch. They preserve the exact selected
numerical data required to reproduce paper-facing postprocessing without
silently rerunning a different experiment.

The promoted manuscript assets live under
`docs/CVT_Module_Formulation/figures/results/`.

## Maintained study layout

A study uses only the pieces it needs:

- `study.json` — machine-readable study identity/configuration;
- `run.py` — maintained local study entry point;
- `verify_study.py` — optional study-specific verifier;
- `README.md` — scientific question, interpretation limits and local commands;
- `infrastructure/`, `experiments/`, `analysis/`, `provenance/`, `tests/`;
- `exploration/` — noncanonical discovery work;
- `artifacts/` — generated and ignored output.

A new CINDER mechanics release receives a new sibling under `results/`; old
release evidence is not silently migrated or relabeled.
