# Repository Layout and Migration Boundary

CINDER is a Python package inside a larger CVT-model project. The repository
contains more than the installable package, so the package boundary must remain
explicit.

```text
cvtModel/
├─ launchTools/         project-local experiments, plots, benchmarks, and tuning scripts
├─ src/cinder/          installed CINDER source
├─ src/cvt_simulator/   legacy source retained during migration
├─ test/cinder/         CINDER regression tests
├─ test/cvt_simulator/  legacy regression tests retained during migration
├─ docs/                CINDER-facing documentation
└─ examples/            small runnable CINDER-only examples
```

## What belongs in `src/cinder`

Only importable CINDER library code belongs here:

```text
contracts/  versioned documents, validation, and result projection
execution/  hybrid integration and transition handling
model/      CVT mechanics and boundary models
results/    traces, reporting, and inspection
studies/    static geometry and actuation studies
```

The package must not import `launchTools`, plotting libraries, repository paths,
or backend frameworks.

## What belongs in `launchTools`

`launchTools` owns project-specific experimentation:

- Baja baseline and reference tuning constants
- graph creation and CSV exports
- parameter sweeps and benchmarks
- paper/validation reproduction scripts
- ad hoc launch, hill, and braking studies

Those scripts may import `cinder.*`, but they are not part of the public CINDER
package contract. CINDER tests must not import `launchTools`: test-only baseline
builders live under `test/cinder/` so the library test suite stays independent
of plotting and project experimentation dependencies.

## The legacy package

While `src/cvt_simulator` and `test/cvt_simulator` are retained, this project’s
`setup.py` explicitly packages only `cinder`. That creates a clean migration
boundary:

```text
pip install -e .
    installs: cinder
    does not install: cvt_simulator
```

When CINDER fully replaces the old package, delete both legacy directories and
remove this migration note. No CINDER import paths or docs should need to
change.
