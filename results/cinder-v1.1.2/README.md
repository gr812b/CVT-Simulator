# Results against CINDER 1.1.2

This directory is the frozen results workspace for the published
**CINDER 1.1.2** mechanics.

```text
CINDER source tag: cinder-v1.1.2
tag commit:        7637a38b4fb9ec21dfb953c1c80a27ec5f389654
PyPI package:      cinder-cvt==1.1.2
Python:            3.12
NumPy:             2.5.2
SciPy:             1.18.1
Matplotlib:        3.11.1
```

Every generated result in this directory must run against the installed
`cinder-cvt==1.1.2` wheel. Do not add the repository's live `cvtModel/src` tree
to `PYTHONPATH`, and do not silently migrate artifacts from an earlier release.

## Results reference model

The shared v1.1.2 Baja reference model uses a **zero-clearance
bilateral/slotted secondary helix**. This is the reference hardware topology
for general results in this release tree.

The signed CINDER 1.1.2 helix torque/force relation, torsional spring,
movable-member inertia, torque sharing and helix kinematics are unchanged. The
reference model simply does not impose a selected-flank compression inequality;
the signed reaction may be carried by either slot flank.

CINDER 1.1.2's public JSON schema does not contain a bilateral-topology switch,
so the frozen public Baja document remains valid release input under
`defaults/baja/`, while `defaults/reference_model/` owns the executable results
interpretation. Studies that consume the shared Baja default call
`defaults.reference_model.decode_reference_case` and therefore inherit the same
reference topology automatically. No interpreter hook, environment variable,
installation step, or global monkey patch is used.

Studies that construct an independent assembly remain explicit by design. The
Ballew benchmark, for example, reconstructs its own non-helical secondary and is
not a consumer of the shared Baja reference model.

## Environment

From repository root on Windows:

```powershell
py -3.12 results/cinder-v1.1.2/bootstrap.py
results\cinder-v1.1.2\.venv\Scripts\Activate.ps1
python results/cinder-v1.1.2/verify_environment.py
```

macOS/Linux:

```bash
python3.12 results/cinder-v1.1.2/bootstrap.py
source results/cinder-v1.1.2/.venv/bin/activate
python results/cinder-v1.1.2/verify_environment.py
```

The bootstrap recreates only this release's `.venv`, installs the frozen
requirements from PyPI, and verifies that CINDER is not coming from a local or
editable checkout. The reference-model helper is ordinary repository code and
does not modify the Python environment.

## Frozen defaults

The defaults tree is split by ownership:

```text
defaults/
├── baja/
│   ├── simulation_case.json
│   ├── tuning.json
│   ├── provenance.json
│   └── README.md
├── reference_model/
│   ├── __init__.py
│   ├── reference_case.py
│   ├── slotted_helix.py
│   ├── policy.json
│   └── README.md
└── verification/
    ├── operating_cases.json
    └── README.md
```

`defaults/baja/simulation_case.json` is the authoritative frozen public solver
input. `defaults/reference_model/` turns that public input into the executable
results reference model. `defaults/verification/operating_cases.json` owns the
reusable verification operating-case vocabulary shared by mechanical invariants,
closure conditioning and later studies.

## Maintained studies

### Mechanical-energy consistency

```powershell
python results/cinder-v1.1.2/studies/energy-consistency/verify_study.py
python results/cinder-v1.1.2/studies/energy-consistency/run.py
```

This is the formal release-level work/energy audit.

### Mechanical invariants / operating-domain capability

```powershell
python results/cinder-v1.1.2/studies/mechanical-invariants/verify_study.py
python results/cinder-v1.1.2/studies/mechanical-invariants/run_reference.py
python results/cinder-v1.1.2/studies/mechanical-invariants/build_capability_map.py
```

The completed bilateral-reference run is summarized by
`CINDER_v1.1.2_mechanical_invariants_recap.pdf`; the invariant study itself is
frozen and this refactor changes ownership/instantiation rather than its physics.

### Closure conditioning

The closure-conditioning study consumes the same shared Baja reference model
and the same verification operating-case library as mechanical invariants.

### Solver convergence

The solver-convergence study consumes the shared bilateral Baja reference model;
its numerical cache revision is bumped by this refactor so pre-refactor cached
trajectories cannot be reused silently.

### Ballew 2015 model-to-model benchmark

This reconstructs its own assembly and remains a **model-to-model comparison**,
not experimental validation.

### Launch then hill climb

This derives from the shared Baja reference model and changes only the declared
road programme and end time.

## Result-tree rule

Each CINDER release owns a separate sibling under `results/`. Existing release
artifacts are immutable historical results; a new CINDER version gets fresh
study executions and fresh generated artifacts.

## Maintained-study repository contract

Study layout and manifest rules are defined in `STUDY_STRUCTURE.md`. The root `run.py` in each maintained study is the canonical reproduction entry point; exploration tooling is excluded from that contract. `verify_all_studies.py` validates the common manifest envelope and then runs each available study-local verifier.

