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

## Results reference topology

The general v1.1.2 results programme uses a **zero-clearance bilateral/slotted
secondary helix**. This is a results-local topology choice, not a patch to the
published CINDER wheel. The production signed helix torque/force, torsional
spring, movable-sheave inertia and shaft-reaction equations are unchanged. The
only removed condition is the selected-unilateral-flank compression inequality:
when the signed reaction changes sign, the opposite slot flank carries it.

The rationale is methodological. Most studies in this tree are intended to
stress belt, closure, hybrid contact and actuator dynamics over a wide operating
domain; selected-flank lift-off from one particular helix hardware design should
not terminate those cases. A dedicated unilateral-versus-slotted study can
isolate that hardware question later.

The frozen public simulation JSON is intentionally left untouched. The results
policy is declared in `defaults/results_reference_model.json` and implemented by
`support/reference_model.py`. There is no auto-import hook or installation step.
Studies that use the shared results decoder get the slotted topology by default;
a dedicated study that wants the published unilateral helix can use CINDER's
normal decoder directly. Result runners should record the chosen reference
model beside generated artifacts.

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
editable checkout. Results-side reference helpers are ordinary repository code;
they do not modify the environment.

## Frozen defaults

`defaults/baja_reference_simulation_case.json` is the authoritative executable
Baja baseline. It contains the complete geometry, contact law, drivetrain
inertias, pulley mechanisms, engine boundary, vehicle/load model, initial state,
integrator settings, and reporting settings.

`defaults/results_reference_model.json` declares the results-side topology policy
applied after the public CINDER assembly is decoded.

`defaults/verification_operating_cases.json` owns the reusable verification case
vocabulary shared by mechanical invariants, closure conditioning and later
studies. It now also stores deterministic reproduction anchors for contact
classes that were shown to be physically valid but unusually difficult to find
with the ordinary search grid.

`defaults/baja_reference_tuning.json` remains a human-readable tuning manifest,
not a second executable source of truth.

See [`defaults/README.md`](defaults/README.md) and
[`defaults/provenance.json`](defaults/provenance.json).

## Maintained studies

### Mechanical-energy consistency

```powershell
python results/cinder-v1.1.2/studies/energy-consistency/verify_study.py
python results/cinder-v1.1.2/studies/energy-consistency/run.py
```

This is the formal release-level work/energy audit. It accounts for boundary
work, stored kinetic/conservative energy, kinetic-slip dissipation, and discrete
impact/capture losses; localizes continuous residuals; checks exact event
closure; and repeats the calculation under quadrature and ODE refinement.

### Mechanical invariants / operating-domain capability

```powershell
python results/cinder-v1.1.2/studies/mechanical-invariants/verify_study.py
python results/cinder-v1.1.2/studies/mechanical-invariants/run_reference.py
python results/cinder-v1.1.2/studies/mechanical-invariants/run_capability_probes.py
python results/cinder-v1.1.2/studies/mechanical-invariants/build_capability_map.py
```

The invariant audit deliberately challenges the model outside one nominal launch:
all gross tangential contact modes/signs, reverse rotation, static rest,
free-shift directions, structural arrivals, geometry-domain closure, field-level
belt admissibility and exact successor states. `CAPABILITY_INTERPRETATION.md`
records how this evidence is being turned into a map of what the retained model
can do comfortably, what is valid but dynamically narrow, and which assumptions
terminate the retained topology.

### Ballew 2015 model-to-model benchmark

```powershell
python results/cinder-v1.1.2/studies/ballew-2015/verify_study.py
python results/cinder-v1.1.2/studies/ballew-2015/run.py
```

This regenerates the force-replay and reconstructed closed-loop comparison
against Ballew's simulated Figure 41/45 traces using CINDER 1.1.2. It remains a
**model-to-model comparison**, not experimental validation.

### Launch then hill climb

```powershell
python results/cinder-v1.1.2/studies/launch-hill-climb/run.py
```

This example derives from the same frozen Baja baseline and changes only the
declared road programme and end time.

## Result-tree rule

Each CINDER release owns a separate sibling under `results/`. Existing release
artifacts are immutable historical results; a new CINDER version gets fresh
study executions and fresh generated artifacts.

Study runners should save the fully resolved input/provenance beside their
results so a figure or metric can always be traced back to the exact release,
results-reference topology, and execution settings.
