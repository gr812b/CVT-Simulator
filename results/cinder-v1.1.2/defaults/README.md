# Frozen Baja reference defaults

The authoritative solver input is:

```text
baja_reference_simulation_case.json
```

It is a complete `cinder_composed_simulation_case` copied semantically from the
released `cinder-v1.1.2` example. `provenance.json` records the source tag,
commit, path, blob SHA, and PyPI package version.

The document contains every runtime input category required for the reference
simulation:

- belt and pulley geometry;
- contact friction coefficients;
- primary/secondary rotating and translating inertias;
- belt density;
- fixed-pivot flyweight geometry and compiled mass moments;
- primary axial spring;
- secondary axial spring;
- secondary torsional spring and helix;
- full-throttle engine torque curve and engine equivalent inertia;
- vehicle mass and wheel rotational inertia;
- final-drive ratio and wheel radius;
- rolling resistance, drag, frontal area, air density, and gravity;
- road profile;
- host initial state;
- five CINDER initial states;
- integration tolerances/method/event settings;
- reporting grid and included observers.

## Shared verification operating cases

`verification_operating_cases.json` is a second kind of release default: it is
**not** one executable simulation, but the canonical vocabulary of controlled
verification case/search recipes used by multiple studies. It owns the common
fixed-boundary inertias, torque/speed/shift search ranges, tangential contact
branch requests, free-shift directions, static-rest recipe, and structural
boundary-arrival recipes.

Mechanical invariants and closure conditioning both consume this same file.
Each study still owns its own numerical guards, maps, convergence settings,
metrics, and PASS/REVIEW/FAIL interpretation. A shared recipe only counts as an
accepted case after CINDER's production classifier and that study's physical
admissibility checks accept the resulting state.

See `verification_operating_cases.README.md` for the ownership split and case
semantics.

## Human tuning manifest

`baja_reference_tuning.json` is deliberately secondary to the executable JSON.
It records physical knobs that are obscured by the runtime representation,
including:

- three flyweights;
- 13.646 g arm/body + 250 g tip hardware per flyweight;
- 35° linear primary ramp, 3 mm C3 blend, 35°→20° circular ramp;
- primary spring stiffness/preload;
- 110 mm secondary spring compression;
- 300° secondary torsional preload;
- 20° helix angle from the circumferential direction;
- 7.556 final drive;
- 0.050 kg·m² engine equivalent inertia.

A study must execute the public simulation document, not this human manifest.
When tuning is swept later, the study should document the physical knob and
construct the corresponding public CINDER input explicitly.

## Release provenance

This baseline is re-frozen for the CINDER 1.1.2 results tree. The source release is `cinder-v1.1.2` at commit `7637a38b4fb9ec21dfb953c1c80a27ec5f389654`; exact source identifiers are recorded in `provenance.json`.
