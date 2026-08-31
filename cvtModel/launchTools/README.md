# CINDER launchTools — physical fixed-pivot results surface

`launchTools` is the thesis/results entry surface for the current Baja CINDER
model. It is intentionally **fixed-pivot only**: result-generation scripts do
not expose the retired point-mass centrifugal-ramp tune or legacy launch
presets.

## Authoritative physical default

Every normal result path resolves to:

- fixed-pivot roller flyweight primary;
- 3 flyweights;
- 13.646 g arm/body mass per flyweight;
- 0.250 kg concentrated tip-hardware/tuning mass per flyweight;
- 35 deg initial straight ramp over 5 mm;
- 3 mm C3 transition;
- circular ramp from 35 deg to 20 deg;
- 20 deg secondary helix;
- 300 deg secondary torsional preload;
- 110 mm secondary compression preload;
- primary compression preload resolved for lower-stop release at 2000 rpm;
- 0.050 kg m^2 engine equivalent inertia;
- current CAD CVT/wheel inertias;
- final-drive reduction 7.556;
- belt contact coefficients mu_s = 0.65 and mu_k = 0.55.

The single launch preset is:

```text
launchTools/presets/fixed_pivot_3200_reference.json
```

`TuneCandidate()` and `BajaTrialConstants()` also default directly to this
physical model. There is no legacy ramp-kind selector in the result-layer
configuration.

The tuning field is named `tip_hardware_mass_per_flyweight_kg` deliberately:
it is the concentrated roller/bolt/nut/fixed-hardware/tuning mass at the
roller-centre station. The 13.646 g arm/body mass is added separately by the
fixed-pivot mass model.

## Results environment

The core `cinder-cvt` package keeps plotting optional, but the launch/result
scripts require the `results` extra:

```powershell
cd cvtModel
python -m pip install -e ".[results]"
```

A development environment may instead use `.[dev]`; that extra also includes
the result plotting dependency.

## Canonical result scripts

Use these directly rather than historical wrapper names:

```powershell
python launchTools/run_route_grade_response.py --no-show
python launchTools/run_actuation_clamping_study.py --no-show
python launchTools/run_geometry_design_study.py --no-show
python launchTools/run_coupling_energy_flow.py --no-show
python launchTools/run_dynamic_actuator_ablation.py --scenario launch --no-show
python launchTools/run_actuator_dynamics_stress_search.py --quick --no-show
python launchTools/run_helix_inertia_torque_scaling_sweep.py --quick --no-show
python launchTools/run_tire_slip_terrain_response.py --no-show
python launchTools/tune_fixed_pivot_default.py
```

Ablation/stress scripts may deliberately compare the full dynamic
fixed-pivot/helix model with quasi-static reductions of the **same hardware**.
Those are mechanism-ablation studies, not legacy hardware defaults.

## Safety rule for thesis/results work

Do not add compatibility fallbacks for retired launch presets or the old
point-mass centrifugal-ramp tuning interface. If an old results command or
preset no longer works, translate the intended experiment onto the current
fixed-pivot baseline rather than restoring old defaults.

The active smoke suite contains `test_launch_tools_fixed_pivot_defaults.py`.
Run:

```powershell
python -m pytest cvtModel/test/smoke
```
