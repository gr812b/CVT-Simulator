# Actuator dynamics: flyweight and secondary-helix coupling

This release-scoped study promotes the existing CINDER actuator-dynamics work
into one reproducible results family for `cinder-cvt==1.1.2`.

## Scientific question

**What changes when the primary fixed-pivot flyweight and secondary
torque-reactive helix are treated dynamically rather than quasi-statically,
and which kinetic/coupling channels cause those differences?**

The primary and secondary mechanisms are kept together deliberately. They are
the two axial--rotational actuator couplings in the same CVT and are most useful
when compared within one four-model ablation.

## What is canonical now

Two experiments are promoted as the present baseline result.

### A. Baseline four-model ablation

The tagged `run_dynamic_actuator_ablation.py` experiment compares:

1. full dynamic;
2. quasi-static flyweight only;
3. quasi-static helix only;
4. fully quasi-static.

It makes two comparisons that must not be conflated:

- **same-state constitutive comparison** -- each actuator model is evaluated at
  the same full-model state and with the same full-model closure solution;
- **independent trajectory consequence** -- all four mechanically consistent
  models are integrated independently.

The quasi-static reductions preserve the same hardware/static force maps.
Mechanism-relative inertia removed from a dynamic actuator law is returned to
the corresponding classical shaft inertia rather than being deleted.

### B. Coupling-energy / generalized-inertia decomposition

The tagged `run_coupling_energy_flow.py` experiment runs the unchanged
full-dynamic baseline and exposes the mechanism behind the ablation:

Primary flyweight:
- shaft-axis kinetic energy;
- pivot/mechanism kinetic energy;
- configuration power delivered to the axial DOF;
- complementary shaft/configuration power;
- reflected generalized shift inertia.

Secondary helix:
- torsional spring potential energy;
- movable-member rotational kinetic energy;
- base-shaft, cross/coupling, and relative-rotation terms;
- reflected generalized shift inertia.

The cross kinetic term is a decomposition term, not an independent physical
energy store.

## What is retained only for exploration

The release-tagged stress search and helix inertia/torque sweep are preserved
under `--exploration`, but **their current parameter grids are not promoted as
final scientific claims**.

They remain useful for:
- discovering operating regions where dynamic corrections become large;
- identifying candidate threshold-crossing cases;
- informing the next, equation-led off-baseline experiment design.

The eventual final off-baseline results should begin from the governing terms
and define physically interpretable control parameters before choosing sweep
axes.

## Reproducibility design

The study does **not** silently import the current working tree's `launchTools`.

`upstream_manifest.json` records the Git blob SHA of every required study
utility from the frozen `cinder-v1.1.2` tag. Before a run, `study_support.py`
materializes those exact bytes with:

```text
git show cinder-v1.1.2:<path>
```

into `work/upstream/`, verifies every blob SHA, and runs them using the active
release-scoped Python environment. The physical CINDER implementation itself is
therefore the installed `cinder-cvt==1.1.2` wheel; the tagged source files here
are study/assembly utilities and quasi-static comparator definitions.

This gives the promoted study release-stable behavior even if `develop`
subsequently changes `cvtModel/launchTools`.

## Run

From the repository root, after activating the existing
`results/cinder-v1.1.2/.venv`:

```powershell
python results/cinder-v1.1.2/studies/actuator-dynamics/verify_study.py
python results/cinder-v1.1.2/studies/actuator-dynamics/run.py
```

The default run executes only the canonical baseline ablation and
coupling-energy decomposition.

Optional exploratory quick runs:

```powershell
python results/cinder-v1.1.2/studies/actuator-dynamics/run.py --exploration quick
```

The original full exploratory grids are intentionally explicit:

```powershell
python results/cinder-v1.1.2/studies/actuator-dynamics/run.py --exploration full
```

They can be expensive and should not be treated as frozen final results merely
because they execute successfully.

Individual entry points are also available under `experiments/`.

## Output layout

```text
artifacts/
├── baseline-ablation/
├── coupling-energy/
├── exploration/
│   ├── stress-search/
│   └── helix-scaling/
├── provenance/
├── summary.json
└── summary.md
```

The baseline subdirectory retains the rich tagged outputs, including:
- trajectory diagnostics;
- actuator contribution rows;
- same-state direct clamp comparisons;
- generalized shift-mass map;
- hybrid transition table;
- per-variant summary;
- the tagged diagnostic figures.

The coupling subdirectory retains the tagged energy/coupling trace and figures.

The study-level `summary.md` and `summary.json` extract only a compact set of
headline magnitudes. They are descriptive run summaries, not frozen manuscript
claims.

## Interpretation boundary

This study is intended to answer whether retained actuator dynamics matter and
why. It is not a tuning study. A small Baja-baseline correction is still a
useful result if it establishes the domain in which a quasi-static reduction is
justified.

Before freezing subtle quantitative conclusions, compare the canonical
trajectory against the separate release-level solver-convergence study once
that verification work is complete.
