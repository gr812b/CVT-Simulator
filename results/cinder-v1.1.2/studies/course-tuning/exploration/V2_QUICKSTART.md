# Course-feature exploration, revision 2

Extract the update ZIP **into `results/cinder-v1.1.2`**, over the existing study.
It replaces/adds study source only. It does not contain an `artifacts/` directory,
shared defaults, a CINDER installation, or changes to the original `inputs/course.json`
and `inputs/competitors.json`. Keep the previously generated campaign.

All commands below run **from `results/cinder-v1.1.2`**, with its environment active.

## 1. Add the requested shift curves to an existing campaign — no simulation

```powershell
$study = "studies/course-tuning/exploration"
$old = "$study/artifacts/course38_w6_h80_v2__screen__58a5425d2888"
python "$study/analysis/shift_curves.py" $old
```

Open `$old/shift_curves.html`. It contains every simulated entrant, not only the
focus cars. Individual curves use road-sector colours. Overall/family curves use
entrant colours, with **secondary RPM on x and primary RPM on y**. Traces stay
in chronological order, retaining backshift loops and repeated speeds. Lines do
not connect across resets or missing solver segments. Sector-crossing edges are
split at their spatial boundary by interpolation on the saved edge.

To regenerate the existing main report with the new gallery linked in:

```powershell
python "$study/analysis/report.py" $old --focus R00 W85 W115 H16 H28 B01 D02
```

Neither command integrates CINDER or changes saved trajectories. The dedicated
shift-curves command writes only the new plot/gallery files and their provenance.
New ordinary fleet runs automatically include the shift curves and feature metrics.

## 2. Prepare the next exploration

```powershell
python "$study/verify_study.py"
python "$study/scans/scan_features.py"
```

Preparation prints the work list and creates `plan.json` and course files, but
runs **no simulations**. The plan lives under `artifacts/feature_explorations/`.
The original road and original 32 competitors remain unchanged.

The default plan has 12 road variants / 52 complete-trajectory case runs:

| Group | Roads | Entrants per road | Purpose |
|---|---:|---:|---|
| Flat limit | One 800 m flat | Eight | Distinguish delayed high ratio from persistent under-shifting over a long observation |
| Secondary hill | 0°, 12°, 18°, 24° | Four | Partial backshift after the whoops, before the descent |
| Cyclic loading | Seven variants | Four | Separate amplitude, wavelength and mean-load effects |

The 0° second-hill control has the **same added road lengths** as the real
second-hill variants. All four therefore finish at 501 m. It is not the original
420 m course mislabeled as a control.

The moderate hill starts after the original 12 m post-cyclic flat, then has an
8 m rise, 45 m hold, 8 m return and 20 m recovery before the original descent.
The severe first hill is unchanged.

The cyclic screens keep the section **36 m long**, with a fixed **6 m physical
entry/exit envelope**:

| Variant | Grade amplitude | Wavelength | Mean grade |
|---|---:|---:|---:|
| `cyc_a12_w6_b0` | ±12° | 6 m | 0° |
| `cyc_a24_w6_b0` | ±24° | 6 m | 0° |
| `cyc_a32_w6_b0` | ±32° | 6 m | 0° |
| `cyc_a32_w3_b0` | ±32° | 3 m | 0° |
| `cyc_a32_w12_b0` | ±32° | 12 m | 0° |
| `cyc_a24_w6_b8` | ±24° | 6 m | +8° |
| `cyc_a0_w6_b8` | 0° | No oscillation | +8° |

The bias-only case shares the same smooth spatial envelope as its oscillating
counterpart. Adding mean load is an explicit separate intervention; it is not
presented as merely making the original whoops faster. Shorter wavelength need
not give larger shift excursions, so both shorter and longer pulses are included.

These remain rolling-grade **longitudinal load probes**, not suspension/wheel
unloading/airborne whoops models. Very steep cyclic grades are stress cases of
that retained vehicle boundary, not a claim about a physically realizable track.

## 3. Run a group at a time, or all groups

```powershell
# Natural first step: the smaller second-hill comparison
python "$study/scans/scan_features.py" --groups mild_hill --execute --jobs 4 --resume

# Stronger cyclic excitation, as separate full-course campaigns
python "$study/scans/scan_features.py" --groups cyclic --execute --jobs 4 --resume

# Eight long-flat probes
python "$study/scans/scan_features.py" --groups flat --execute --jobs 4 --resume

# Equivalent combined work list
python "$study/scans/scan_features.py" --execute --jobs 4 --resume
```

The default feature settings use **research**, not the earlier screen preset:
`rtol=1e-4`, `atol=1e-7`, maximum step 10 ms, diagnostic spacing 10 ms. This gives
more reporting resolution for the short cyclic periods. Exact hybrid transitions
and accepted native solver states remain saved. Refine selected cases with
`--preset tight` before making final comparisons.

For a smaller initial execution:

```powershell
python "$study/scans/scan_features.py" --groups mild_hill --variants mild_hill_18 --cars R00 W85 --execute --jobs 2 --resume
python "$study/scans/scan_features.py" --groups cyclic --variants cyc_a32_w3_b0 cyc_a32_w12_b0 --cars R00 B01 --execute --jobs 2 --resume
```

The grouped runner launches each road variant in sequence and runs its entrants
in separate processes. It retains failed/censored cases, proceeds to the next
variant, and writes a combined `index.html` beside `plan.json` as results arrive.
`--no-plots` defers the normal per-campaign graphics; the smaller cross-variant
feature comparisons are still produced. Every campaign retains its CSV/JSON/NPZ
files for later reporting.

To rebuild the cross-variant report without rerunning:

```powershell
python "$study/analysis/compare_features.py" PATH_TO_FEATURE_PLAN/plan.json
```

Use the printed plan path. Group selections share a plan when the configuration,
preset, entrant override and code are unchanged. Changed inputs/code get new
fingerprints. Runtime never changes a course for one entrant. No saved state is
reset at a feature, and no CVT force, friction, shift, or speed trajectory is imposed.

## 4. New entrants

`inputs/competitors_features.json` contains the original 32 entries unmodified,
plus:

| ID | Difference from R00 |
|---|---|
| U70 | Flyweight tip mass ×0.70 |
| U55 | Flyweight tip mass ×0.55 |
| U40 | Flyweight tip mass ×0.40 — extreme control |
| P130 | Primary spring initial compression ×1.30 |
| S480 | Secondary torsional pretwist 480° |
| UHR | Tip mass ×0.70, 16° helix, 360° secondary pretwist |

The long-flat group uses R00, D02 and these six. The road-feature groups use R00,
W85, H28 and B01 to expose primary and secondary tuning differences without
repeating all 38 cars in every preliminary road variant. `--cars` overrides that
selection. The common dynamics and boundary checks remain active for every car.

These settings are mechanism-motivated stress probes; spring travel, coil bind,
component stress and available hardware are not separately certified.

## 5. What to inspect before combining features

Every campaign now writes `feature_metrics.csv` and `cyclic_cycle_metrics.csv`.
The cross-variant report adds local overlays for each car: shift, shift rate,
primary RPM and vehicle speed versus distance into the feature.

**Flat:** report whether high ratio is reached, where it first occurs, the maximum
shift, and the last 10 s of shift/speed behavior. "Did not reach full shift on the
120 m launch flat" is not "can never reach full shift." Even a very flat 800 m
trace is finite-time evidence, not an asymptotic proof.

**Moderate hill:** inspect the maximum fall from a preceding shift maximum, the
minimum active-shift fraction and low-ratio-seat occupancy. The optional nomination
flag requires a completed added hill, at least 0.25 mm drawdown, no sampled
low-ratio-seat state, minimum active fraction above 0.003, and no case review flag.
These are reporting criteria, not mechanics or switching tolerances.

**Cyclic:** the full range of shift can mostly be ordinary continuing upshift.
Compare opening travel, maximum backshift drawdown, stop occupancy and per-cycle
modulation instead. The latter fits an offset, a linear spatial trend and one
sin/cos pair; its peak-to-peak amplitude summarizes modulation, not a transfer
function or independently isolated causal response. Only fully traversed cycles
with adequate samples enter that summary. Exact event timing remains in events.json.

The 0.1 mm/s backshift-duration threshold is likewise a reporting threshold.
Durations are clipped segmentwise on saved samples; final publication event times
should use the exact records. Missing sectors, model-domain exits, numerical
errors and progress censoring remain distinct from clean performance outcomes.

**Do not choose only the road with the largest wiggle.** Prefer a retained-domain
case that produces an interpretable difference across tunes. Once the features
are chosen, combine them into one course and rerun the chosen fleet end to end;
separate feature trials cannot be spliced into a common trajectory.
