# Ideal CVT track study

This standalone launch-tool microframework asks:

> How do finite CVT ratio limits, final-drive gearing, and tire radius change a Baja vehicle's performance around a physical track, relative to an ideal unbounded CVT that can hold the engine at peak power?

It intentionally does **not** import core CINDER. The powertrain uses the bounded/infinite ideal-CVT comparison, independent wheel and vehicle states, and a smooth tire-slip law.

## Public entrypoints

```bash
python launchTools/ideal_cvt_track_study/run_single.py
python launchTools/ideal_cvt_track_study/run_sweep.py
```

Choose another track with `--track`:

```bash
python launchTools/ideal_cvt_track_study/run_single.py \
  --track launchTools/ideal_cvt_track_study/tracks/long_obstacle_course.json
```

Use `--no-show` to save plots without opening windows.

## Track builder

Physical track construction lives in:

```text
track_builder/
├── README.md
├── base_section.py
├── core.py
├── curvature_segment.py
├── log_crossing.py
├── profile_obstacle.py
├── rough_patch.py
├── slalom_segment.py
├── surface_patch.py
├── track.py
└── whoop_train.py
```

Read [`track_builder/README.md`](track_builder/README.md) for the complete equations, JSON schema, feature parameters, code-builder example, and model limitations.

A video-review intake workbook is included at `track_builder/templates/track_video_measurement_intake.xlsx`.

The supported physical feature overlays are:

- surface patches;
- banked plan-view curvature segments with friction-circle longitudinal limits;
- smooth alternating slalom segments;
- surface patches;
- deterministic rough/rutted patches with load variation and distributed loss;
- energy-based log crossings;
- measured-profile bumps, pipes, tires, holes, dips, and local drop/recovery obstacles;
- sinusoidal whoop trains with grade, normal-load variation, and optional unresolved damping loss.

Driver top-speed choices, traffic, forced braking, hesitation, and Monte Carlo other-car disturbances remain separate from the physical track.

## Supplied tracks

### Lot M baseline

`tracks/lot_m.json` is the provisional 600 m baseline:

1. 150 m gravel flat;
2. 135 m gravel downhill at $-5^\circ$;
3. 15 m gravel hairpin;
4. 150 m asphalt uphill at $+5^\circ$;
5. 135 m asphalt flat;
6. 15 m asphalt hairpin and lap end.

The former arbitrary 5.5 m/s speed caps are now physical curvature features whose local friction-limited corner speeds are approximately 5.5 m/s.

### Long mixed obstacle course

`tracks/long_obstacle_course.json` is a synthetic 6000 m development track, exactly ten times the Lot M distance. It contains:

- varied grades and surfaces;
- banked and unbanked curvature;
- a slalom;
- mud, deep sand, wet grass, and rocky ruts;
- three log crossings;
- pipe and hole profile obstacles;
- two whoop trains.

It is intended to exercise the framework, not to represent a measured course. `tracks/feature_showcase.json` is a shorter validation track containing every built-in feature type.

## Ideal-CVT model

The bounded perfect CVT uses the speed ratio

$$
q=\frac{\omega_e}{\omega_s},
$$

where $\omega_e$ is engine speed and $\omega_s$ is secondary-shaft speed.

- `maximum_speed_ratio` is the low-speed, high-reduction end;
- `minimum_speed_ratio` is the high-speed, low-reduction end;
- the infinite-CVT reference has no ratio bounds.

### Behavior at the ratio limits

The ratio required to hold the engine at its peak-power speed is

$$
q_{\mathrm{req}}
=
\frac{\omega_{e,\mathrm{target}}}{\omega_s}.
$$

The bounded model has three operating regions.

#### Maximum ratio: launch and low vehicle speed

When

$$
q_{\mathrm{req}}>q_{\max},
$$

the CVT is held at

$$
q=q_{\max}.
$$

With the ideal launch clutch enabled, the engine is placed directly at its peak-power speed while the clutch slips:

$$
\omega_e=\omega_{e,\mathrm{target}}.
$$

Engine torque still comes from the actual torque curve at that engine speed. Wheel drive torque is

$$
\tau_w
=
\tau_e\,q_{\max}\,i_f\,\eta,
$$

where $i_f$ is the final-drive ratio and $\eta$ is transmission efficiency.

The model does not launch from a direct $P/v$ force expression. Wheel speed, vehicle speed, tire slip, and longitudinal tire force are solved and integrated forward in time. During clutch slip, the difference between engine-side power and power reaching the wheels is reported as clutch-loss power.

As wheel speed rises, the synchronous engine speed at $q_{\max}$ reaches the target engine speed. The clutch becomes synchronous and the CVT enters its continuously variable region.

#### Inside the available ratio range

When

$$
q_{\min}\le q_{\mathrm{req}}\le q_{\max},
$$

the CVT selects

$$
q=q_{\mathrm{req}}
$$

and holds

$$
\omega_e=\omega_{e,\mathrm{target}}.
$$

This is the ideal continuously variable region. There is no shift delay, actuator limit, belt-slip loss, or transient ratio error. The engine remains at its peak-power operating point unless throttle is reduced by the driver model.

#### Minimum ratio: high vehicle speed

When

$$
q_{\mathrm{req}}<q_{\min},
$$

the CVT is held at

$$
q=q_{\min}.
$$

The powertrain then behaves like a fixed high gear:

$$
\omega_e=q_{\min}\omega_s.
$$

The engine is no longer guaranteed to remain at peak-power speed. Torque and power are evaluated from the actual torque curve at the resulting engine RPM, and the difference from available peak power is reported as operating-point opportunity loss.

### Integrated vehicle response

The wheel and vehicle remain separate dynamic states. Tire longitudinal force comes from tire slip rather than being imposed directly from engine power. Grade, rolling resistance, aerodynamic drag, cornering demand, obstacle resistance, and terrain-dependent normal load act on the vehicle during integration.

The launch and CVT controls are intentionally idealized:

- engine rotational inertia is omitted;
- engine speed can move immediately to the target RPM;
- clutch torque capacity and engagement dynamics are not modeled;
- CVT ratio changes inside the available range are instantaneous.

## Single configuration

```bash
python launchTools/ideal_cvt_track_study/run_single.py
```

Useful overrides:

```bash
python launchTools/ideal_cvt_track_study/run_single.py \
  --minimum-cvt-ratio 1.13 \
  --maximum-cvt-ratio 4.92 \
  --final-drive-ratio 7.556 \
  --wheel-radius-in 11
```

The command writes bounded/reference traces, summaries, resolved inputs, and plots for:

- speed versus distance;
- CVT ratio and engine RPM;
- engine/transmitted power and CVT opportunity loss in hp;
- tire slip and tire utilization;
- all loss-power channels in hp, including obstacle loss;
- compiled track profile and physical features;
- the combined dashboard.

Per-feature summaries include entry speed, exit speed, minimum speed, time, distance, obstacle loss, tire-slip loss, traction-limited time, and time at the CVT ratio bounds.

The default maximum simulation time is chosen from track length. Override it with `--maximum-time-s` when needed.

## Parameter sweep

```bash
python launchTools/ideal_cvt_track_study/run_sweep.py
```

A one-variable final-drive sweep is:

```bash
python launchTools/ideal_cvt_track_study/run_sweep.py \
  --minimum-cvt-ratios 1.1306679709 \
  --maximum-cvt-ratios 4.9230769231 \
  --final-drive-ratios 3.5 4.0 4.5 5.0 5.5 6.0 6.5 7.0 7.556 8.0 8.5 9.0 10.0 11.0 \
  --wheel-radii-in 11 \
  --independent-variable final_drive_ratio
```

The sweep writes:

- independent variable versus average opportunity-loss power in hp;
- independent variable versus lap time;
- lap time versus average opportunity-loss power;
- engine-band and high-ratio saturation plots;
- a ratio-bound heatmap when both CVT limits vary;
- fastest-configuration rankings.

## Metrics

Each run reports:

- lap time, average speed, and maximum speed;
- time and distance at low ratio, variable ratio, and high ratio;
- time and distance outside the target engine band;
- traction-limited and tire-slip time;
- engine and transmitted energy;
- clutch and off-peak opportunity loss;
- tire-slip, braking, rolling, aerodynamic, and obstacle losses;
- net grade work;
- per-section metrics;
- per-feature metrics;
- lap penalty relative to the infinite-CVT reference.

JSON and CSV outputs retain energy totals in kJ. Power and loss-rate plots use hp. Sweep loss plots use lap-average equivalent loss power:

$$
\overline{P}_{\mathrm{loss}}
=
\frac{E_{\mathrm{loss}}}{t_{\mathrm{lap}}}.
$$

## Interpretation cautions

This is a design-trend tool, not a CINDER replacement or a full vehicle-dynamics solver.

- The CVT is perfect inside its ratio bounds.
- There are no belt/sheave dynamics or shift delays.
- The launch clutch is idealized.
- Tire and driver models are intentionally reduced.
- Curvature is represented by lateral force demand and a friction circle.
- Logs and whoops represent longitudinal consequences rather than suspension motion.
- Track dimensions and feature parameters require calibration before absolute predictions should be trusted.
