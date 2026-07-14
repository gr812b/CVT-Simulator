# Track builder

This folder defines the **physical track** used by the standalone ideal-CVT study. It contains track geometry, surfaces, and terrain features only.

Driver choices and external disturbances do not belong in the track definition. Future traffic, forced braking, hesitation, temporary driver speed targets, and Monte Carlo other-car effects should be separate scenario layers applied after the physical track has been sampled.

## Overview

At distance $x$, vehicle speed $v$, vehicle mass $m$, and gravitational acceleration $g$, the builder combines one base section with any active feature overlays.

A compiled track sample contains:

- elevation, $z(x)$;
- grade angle, $\theta(x)$;
- plan-view curvature, $\kappa(x)$;
- tire-road friction coefficient, $\mu(x)$;
- rolling-resistance coefficient, $C_{rr}(x)$;
- normal-load scale, $n_N(x,v)$;
- additional obstacle resistance, $F_{\mathrm{obs}}(x,v)$;
- a physical curvature-limited speed;
- active feature names and feature types.

The standalone longitudinal vehicle model then uses

$$
m\dot v
=
F_{\mathrm{tire}}
-mg\sin\theta
-C_{rr}N\,\operatorname{sgn}(v)
-F_{\mathrm{aero}}
-F_{\mathrm{obs}}.
$$

For unbanked terrain, the approximate tire normal load is

$$
N = mg\cos\theta\;n_N.
$$

For banked curvature, the compiler instead uses the bank-aware normal and lateral force relations described under `CurvatureSegment`.

This remains a one-dimensional longitudinal model. It represents the longitudinal consequences of terrain, but it does not model suspension travel, chassis pitch, axle-specific wheel contact, landing impacts, or airborne motion.

## Package layout

```text
track_builder/
├── README.md
├── __init__.py
├── base_section.py
├── core.py
├── curvature_segment.py
├── log_crossing.py
├── profile_obstacle.py
├── rough_patch.py
├── slalom_segment.py
├── surface_patch.py
├── templates/
│   └── track_video_measurement_intake.xlsx
├── track.py
└── whoop_train.py
```

Each physical feature type has its own implementation file. The corresponding governing equations are repeated in that file's module and class comments.

---

## Base sections

### `base_section.py` — `TrackSection`

A `TrackSection` defines a sequential portion of the base terrain:

- section length;
- constant grade;
- base friction coefficient;
- base rolling-resistance coefficient;
- surface label.

For a section with constant grade angle $\theta$,

$$
\frac{dz}{dx}=\tan\theta.
$$

The section elevation therefore changes linearly with distance:

$$
z(x)=z_0+(x-x_0)\tan\theta.
$$

Feature overlays may modify the section's surface, curvature, elevation, slope, normal load, or obstacle resistance.

---

## Surface patches

### `surface_patch.py` — `SurfacePatch`

A `SurfacePatch` modifies tire-road friction and rolling resistance over a distance interval.

The nominal longitudinal tire-force limit is

$$
F_{\mathrm{tire,max}}=\mu(x)N(x).
$$

Rolling resistance is

$$
F_{rr}=C_{rr}(x)N(x)\operatorname{sgn}(v).
$$

A surface patch can override or scale $\mu$ and $C_{rr}$. Typical uses include:

- mud;
- deep sand;
- wet grass;
- loose gravel;
- compact dirt;
- short low-traction regions.

A surface patch describes physical ground conditions. It should not be used to represent traffic, driver hesitation, or an arbitrary forced speed limit.

---

## Curvature segments

### `curvature_segment.py` — `CurvatureSegment`

A `CurvatureSegment` defines a constant plan-view turn radius $R$, direction, and optional bank angle $\beta$. Its signed curvature is

$$
\kappa=\pm\frac{1}{R}.
$$

Positive bank angle assists the specified turn; negative bank is adverse camber. With grade angle $\theta$, the reduced road-normal and road-lateral force demands are

$$
N
=
m\left[g\cos\theta\cos\beta+v^2|\kappa|\sin\beta\right]n_N,
$$

$$
F_y
=
m\left[v^2|\kappa|\cos\beta-g\cos\theta\sin\beta\right].
$$

The remaining longitudinal tire capacity follows

$$
F_{x,\max}
=
\sqrt{\max\left((\mu N)^2-F_y^2,0\right)}.
$$

For $\beta=0$, this reduces to the ordinary flat-corner friction-circle model. The track stores physical curvature and banking only. Driver braking anticipation remains outside the track definition.

Parameters:

- `start_m`, `length_m`;
- `radius_m`;
- `direction`: `left` or `right`;
- `bank_angle_degrees`: positive when the bank supports the turn.

---

## Slalom segments

### `slalom_segment.py` — `SlalomSegment`

A `SlalomSegment` is a smooth sequence of alternating bends. Let $\xi$ be local distance through a slalom of length $L$, $n$ be the number of bends, and $\kappa_{\max}$ be peak curvature. Then

$$
\kappa(\xi)
=
s\,\kappa_{\max}\sin\left(\frac{n\pi\xi}{L}\right),
$$

where $s=+1$ for an initial left bend and $s=-1$ for an initial right bend. One half-wave is one bend.

Parameters:

- `start_m`, `length_m`;
- `bend_count`;
- `peak_curvature_1_per_m`, or equivalently minimum radius $1/\kappa_{\max}$;
- `initial_direction`.

This is useful when video shows repeated left-right gates but does not justify entering many separate curvature segments.

---

## Rough patches and ruts

### `rough_patch.py` — `RoughPatch`

A `RoughPatch` represents distributed ruts, rocks, washboard, or generally rough terrain. It combines surface changes, normal-load variation, and unresolved longitudinal loss.

For local distance $\xi$, roughness wavelength $\lambda$, amplitude $a_N$, and phase $\varphi$,

$$
k_N(\xi)
=
\operatorname{clip}\left[1+a_N\sin\left(\frac{2\pi\xi}{\lambda}+\varphi\right),k_{\min},k_{\max}\right].
$$

The unresolved resistance is

$$
F_{\mathrm{rough}}(v)
=
e'_{\mathrm{rough}}+k_vv^2.
$$

Here $e'_{\mathrm{rough}}$ is energy loss per metre, numerically equal to force in newtons, and $k_v$ controls speed-dependent impact loss.

Parameters:

- `roughness_wavelength_m`;
- `normal_load_variation_fraction`;
- `phase_degrees`;
- minimum and maximum normal-load scales;
- `energy_loss_j_per_m`;
- `speed_squared_resistance_coefficient_kg_per_m`;
- optional friction and rolling-resistance overrides or multipliers;
- optional surface label.

This predicts longitudinal consequences only; it does not predict suspension travel or individual-wheel contact.

---

## Measured profile obstacles

### `profile_obstacle.py` — `ProfileObstacle`

A `ProfileObstacle` is a smooth measured obstacle for bumps, pipes, tires, holes, dips, and local drop/recovery shapes. It uses a signed raised-cosine profile over length $L$:

$$
z(\xi)
=
\frac{h}{2}\left[1-\cos\left(\frac{2\pi\xi}{L}\right)\right],
$$

$$
\frac{dz}{dx}
=
\frac{h\pi}{L}\sin\left(\frac{2\pi\xi}{L}\right),
$$

$$
\frac{d^2z}{dx^2}
=
\frac{2\pi^2h}{L^2}\cos\left(\frac{2\pi\xi}{L}\right).
$$

Positive $h$ represents a bump, pipe, or tire. Negative $h$ represents a hole, dip, or local drop and recovery. A permanent net elevation change belongs in the base sections.

The rigid-following normal-load scale is

$$
k_N
=
\operatorname{clip}\left(1+\frac{v^2z''}{g},k_{\min},k_{\max}\right).
$$

Optional unresolved impact loss is distributed with

$$
\psi(\xi)=\frac{1-\cos(2\pi\xi/L)}{L},
$$

$$
F_{\mathrm{loss}}
=
\left(E_{\mathrm{fixed}}+k_{\mathrm{impact}}v^2\right)\psi(\xi).
$$

Parameters:

- `profile_kind`: `bump`, `pipe`, `tire`, `hole`, `dip`, or `drop_recovery`;
- `start_m`, `length_m`;
- signed `vertical_amplitude_m`;
- fixed and speed-dependent impact-loss terms;
- traction multiplier;
- minimum and maximum normal-load scales.

---

## Log crossings

### `log_crossing.py` — `LogCrossing`

A `LogCrossing` is represented as localized work that must be supplied by the vehicle.

The required obstacle energy is

$$
E_{\mathrm{log}}
=
mghf_{\mathrm{lift}}
+k_{\mathrm{impact}}v^2.
$$

Here:

- $h$ is the log height;
- $f_{\mathrm{lift}}$ is the effective fraction of that height through which the vehicle centre of mass is raised;
- $k_{\mathrm{impact}}$ controls speed-dependent impact loss.

The energy is distributed smoothly over crossing length $L$. Let $\xi\in[0,L]$ be local distance through the crossing. The normalized raised-cosine distribution is

$$
\psi(\xi)
=
\frac{1-\cos\left(2\pi\xi/L\right)}{L}.
$$

It satisfies

$$
\int_0^L\psi(\xi)\,d\xi=1.
$$

The added resistance force is therefore

$$
F_{\mathrm{log}}(\xi,v)
=
E_{\mathrm{log}}(v)\,\psi(\xi).
$$

Consequently,

$$
\int_0^L F_{\mathrm{log}}\,d\xi
=
E_{\mathrm{log}}.
$$

This removes the intended energy continuously instead of applying an instantaneous speed jump. It is an effective longitudinal obstacle model, not a wheel-climb or suspension simulation.

---

## Whoop trains

### `whoop_train.py` — `WhoopTrain`

A `WhoopTrain` uses a repeated smooth elevation profile. For one wavelength $\lambda$, let $\xi\in[0,\lambda]$ be local distance through a whoop. The elevation is

$$
z(\xi)
=
\frac{h}{2}
\left[
1-\cos\left(\frac{2\pi\xi}{\lambda}\right)
\right].
$$

The first spatial derivative is

$$
\frac{dz}{dx}
=
\frac{h\pi}{\lambda}
\sin\left(\frac{2\pi\xi}{\lambda}\right).
$$

The second spatial derivative is

$$
\frac{d^2z}{dx^2}
=
\frac{2\pi^2h}{\lambda^2}
\cos\left(\frac{2\pi\xi}{\lambda}\right).
$$

The local grade angle is obtained from

$$
\theta=\tan^{-1}\left(\frac{dz}{dx}\right).
$$

A rigid-following vertical-acceleration estimate is

$$
a_z
\approx
v^2\frac{d^2z}{dx^2}
+\dot v\frac{dz}{dx}.
$$

The current reduced model uses the dominant curvature term in its normal-load estimate:

$$
N
\approx
m\left[
g\cos\theta
+v^2\frac{d^2z}{dx^2}
\right].
$$

The configured minimum and maximum normal-load scales keep this approximation bounded. Optional `energy_loss_j_per_whoop` represents unresolved suspension and tire dissipation. That energy is distributed over each wavelength with a normalized raised-cosine force.

This feature does **not** predict:

- suspension travel;
- bottoming;
- pitch dynamics;
- front/rear axle phasing;
- landing loads;
- airborne trajectory.

---

## Combining feature overlays

A track has sequential base `sections` and optional physical `features`. Multiple features may overlap.

The compiler combines their effects as follows:

- surface overrides are applied in feature order;
- friction and traction multipliers are combined;
- curvature and bank-angle contributions are added;
- elevation and slope contributions are added;
- extra obstacle resistance forces are added;
- normal-load multipliers are combined and then bounded.

Feature intervals must remain inside the total base-section length.

---

## JSON format

```json
{
  "name": "Example track",
  "notes": "Measured or provisional source notes.",
  "sections": [
    {
      "name": "Dirt straight",
      "length_m": 200.0,
      "grade_degrees": 0.0,
      "friction_coefficient": 0.60,
      "rolling_resistance_coefficient": 0.03,
      "surface": "dirt"
    }
  ],
  "features": [
    {
      "type": "surface_patch",
      "name": "Mud",
      "start_m": 40.0,
      "length_m": 25.0,
      "friction_coefficient": 0.35,
      "rolling_resistance_coefficient": 0.09,
      "surface": "mud"
    },
    {
      "type": "curvature_segment",
      "name": "Hairpin",
      "start_m": 100.0,
      "length_m": 20.0,
      "radius_m": 8.0,
      "direction": "left"
    },
    {
      "type": "rough_patch",
      "name": "Ruts",
      "start_m": 120.0,
      "length_m": 30.0,
      "roughness_wavelength_m": 2.5,
      "normal_load_variation_fraction": 0.25,
      "energy_loss_j_per_m": 30.0,
      "speed_squared_resistance_coefficient_kg_per_m": 0.15
    },
    {
      "type": "slalom_segment",
      "name": "Slalom",
      "start_m": 150.0,
      "length_m": 35.0,
      "bend_count": 5,
      "peak_curvature_1_per_m": 0.08,
      "initial_direction": "left"
    },
    {
      "type": "profile_obstacle",
      "name": "Pipe",
      "start_m": 188.0,
      "length_m": 1.2,
      "vertical_amplitude_m": 0.15,
      "profile_kind": "pipe",
      "impact_loss_coefficient_kg": 3.0
    },
    {
      "type": "log_crossing",
      "name": "Log",
      "position_m": 145.0,
      "crossing_length_m": 1.4,
      "height_m": 0.22,
      "effective_lift_fraction": 0.35,
      "impact_loss_coefficient_kg": 8.0,
      "traction_multiplier": 0.85
    },
    {
      "type": "whoop_train",
      "name": "Whoops",
      "start_m": 160.0,
      "count": 8,
      "wavelength_m": 3.0,
      "height_m": 0.18,
      "energy_loss_j_per_whoop": 140.0,
      "minimum_normal_load_scale": 0.10,
      "maximum_normal_load_scale": 1.9,
      "traction_multiplier": 0.95
    }
  ]
}
```

## Code-defined tracks

JSON is the normal user path, but the same objects can be assembled in Python:

```python
from track_builder import CurvatureSegment, TrackBuilder, TrackSection

track = (
    TrackBuilder("Code track")
    .add_section(
        TrackSection(
            name="Gravel",
            length_m=200.0,
            grade_degrees=0.0,
            friction_coefficient=0.65,
            rolling_resistance_coefficient=0.025,
            surface="gravel",
        )
    )
    .add_feature(
        CurvatureSegment(
            name="Turn",
            start_m=100.0,
            length_m=20.0,
            radius_m=8.0,
            direction="left",
        )
    )
    .build()
)
```

## Supplied tracks

### Lot M

`../tracks/lot_m.json` is the provisional 600 m Lot M course. Its former 5.5 m/s hairpin caps are represented by physical curvature radii chosen to produce approximately the same friction-limited corner speeds on the local surfaces.

### Long obstacle course

`../tracks/long_obstacle_course.json` is a synthetic 6000 m development course, exactly ten times the Lot M distance. It includes:

- varied grades and surfaces;
- five curvature sections;
- mud, deep sand, and wet grass;
- three log crossings;
- two whoop trains.

Run the long course with the unchanged public entrypoint:

```bash
python launchTools/ideal_cvt_track_study/run_single.py \
  --track launchTools/ideal_cvt_track_study/tracks/long_obstacle_course.json
```

The maximum simulation time scales automatically with track length unless `--maximum-time-s` is supplied.

## Track-related outputs

Single runs retain the ordinary speed, CVT-ratio, RPM, power, tire, dashboard, and sweep outputs. They additionally write:

- `06_track_profile_and_features.png`;
- active feature names and types in every trace row;
- obstacle resistance force and loss-power channels;
- per-feature entry speed, exit speed, minimum speed, elapsed time, distance, obstacle loss, tire-slip loss, ratio-bound time, and traction-limited time.

The track profile plot includes:

- elevation;
- grade;
- curvature;
- surface/friction information;
- normal-load scale;
- obstacle resistance;
- lateral-force demand;
- active features.

## Deliberate limitations

- The vehicle follows a one-dimensional path coordinate.
- There are no suspension, pitch, roll, or axle-specific states.
- There is no airborne integration.
- Logs and whoops are effective longitudinal-energy and normal-load models.
- Curvature uses a friction circle rather than full yaw dynamics.
- Obstacle parameters require calibration from footage, GPS, or telemetry.
- Traffic and driver disturbances are intentionally outside the track package.

---

## Video measurement intake workbook

`templates/track_video_measurement_intake.xlsx` contains the supplied provisional course rows, cumulative distance formulas, a proposed builder mapping for every row, and obstacle-specific questions to answer while reviewing video.

The workbook separates:

- the original observations;
- the proposed physical feature type;
- the measurements still needed;
- user answers and confidence;
- feature-level parameter and estimation guides.

It is an intake aid, not an automatic free-text importer. Ambiguous descriptions should remain visibly unresolved until measurements are available.
