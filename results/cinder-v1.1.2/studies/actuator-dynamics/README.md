# Actuator dynamics — baseline consequence and quasi-static validity

This is the official CINDER `v1.1.2` results study for the two actuator
axial--rotational couplings:

- the primary fixed-pivot flyweight mechanism;
- the secondary torque-reactive helix / movable sheave.

They remain one study because the scientific question is common:

> **When does treating the actuator as a dynamic mechanical subsystem change
> the force prediction or the CVT trajectory, and when is a quasi-static
> actuator approximation justified?**

## Four-part result

### 1. Baseline ablation

The actual Baja launch is integrated with four mechanically consistent models:

1. full dynamic;
2. quasi-static flyweight;
3. quasi-static helix;
4. both quasi-static.

The experiment separately reports:

- **same-state constitutive difference**, evaluating the alternative actuator
  laws on the same full-model state and closure solution;
- **trajectory consequence**, integrating every model independently.

Mechanism-relative inertia removed by an ablation is returned to the ordinary
shaft inertia. No hardware mass is silently deleted.

### 2. Coupling-energy decomposition

The full baseline is decomposed into the energy and generalized-inertia
channels that make the two dynamic couplings visible.

For the flyweight this includes pivot kinetic energy and exact configuration
power associated with the position-dependent shaft inertia. For the helix it
includes spring energy and the movable member's base-shaft, cross, and
relative-rotation kinetic terms.

A large direct generalized `M_ss` contribution is **not** interpreted by itself
as a large trajectory effect. The shaft and shift equations are coupled; the
ablation and controlled-response experiments provide the consequence measure.

### 3. Equation-derived quasi-static validity envelopes

The old arbitrary scaling sweep has been removed.

Instead, the study defines exact fractional dynamic corrections from the
actuator equations.

Primary:

\[
\Pi_{\mathrm{fw}}
=
\frac{
\left|
I_f q_x^2\ddot{x}_p
+
I_f q_x q_{xx}\dot{x}_p^2
\right|
}{
\left|\tfrac12\omega_p^2J_f'(x_p)\right|
}.
\]

The result reports the shift acceleration or shift speed required to produce
1%, 5%, 10%, and 20% correction at representative engaged positions and shaft
speeds. Acceleration and curvature terms are shown separately because they can
reinforce or cancel.

Secondary:

\[
\Pi_h
=
\frac{
I_M|\alpha_s+\ddot{\theta}|
}{
|f\tau_s+k_\theta(\theta_{\rm pre}-\theta)|
}.
\]

Here the common `dtheta/dx_s` force multiplier cancels exactly. This makes the
quasi-static validity boundary a direct competition between movable-member
inertial torque and quasi-static reacted torque. Geometry still enters through
the helix state and through

\[
\ddot{\theta}
=
\frac{d\theta}{ds}\ddot{s}
+
\frac{d^2\theta}{ds^2}\dot{s}^2.
\]

### 4. Controlled transient validation

The old "largest score wins" stress search has also been removed as a result
definition.

Instead, finite smooth shaft-torque ramps are used only as **experiment-design
inputs**. The full model is restarted from naturally reached 20%, 50%, and 80%
engaged-shift states. A modest deterministic grid of ramp magnitude and ramp
duration is screened, and every case is classified as:

- clean continuous;
- contact switching;
- impact/reset.

For each actuator, the official validation set selects clean-continuous cases
whose **achieved** peak \(\Pi\) is nearest to 1%, 5%, 10%, and 20%. If the
available physical screen cannot reach a target cleanly, the study reports that
target as unreached rather than substituting a reset case.

Each selected case is rerun with the corresponding quasi-static model and with
zero-perturbation controls. The trajectory consequence is evaluated as

\[
(\text{QS stress}-\text{QS control})
-
(\text{full stress}-\text{full control}),
\]

so ordinary baseline offsets between independently conditioned models do not
masquerade as response error.

This gives a direct paper-facing chain:

\[
\text{actuator equation}
\rightarrow
\Pi
\rightarrow
\text{quasi-static validity boundary}
\rightarrow
\text{controlled trajectory consequence}.
\]

## Why this replaces the old exploratory sweeps

The tagged broad stress-search and `I_M x torque` sweep were valuable while
finding interesting regimes, but their axes were not themselves the scientific
result. They have been removed from this release-scoped study.

The new off-baseline result starts from the equations, defines what "dynamic
importance" means, uses input sweeps only to reach controlled values of that
measure, and reports the achieved measure explicitly.

## Reproducibility

CINDER mechanics are supplied only by the published
`cinder-cvt==1.1.2` environment.

The baseline study utilities are materialized from the exact
`cinder-v1.1.2` Git tag and verified by Git blob SHA. Mutable `develop`
`launchTools` are never imported silently.

The new validity-envelope and controlled-transient experiment definitions are
stored directly in this release-scoped results directory.

## Run

Verify first:

```powershell
python results/cinder-v1.1.2/studies/actuator-dynamics/verify_study.py
```

Complete official study:

```powershell
python results/cinder-v1.1.2/studies/actuator-dynamics/run.py
```

The controlled-transient screen is the longest stage. During development the
study can be run incrementally:

```powershell
python results/cinder-v1.1.2/studies/actuator-dynamics/run.py --through baseline
python results/cinder-v1.1.2/studies/actuator-dynamics/run.py --through coupling
python results/cinder-v1.1.2/studies/actuator-dynamics/run.py --through envelopes
```

Individual experiment runners are under `experiments/`.

## Artifacts

```text
artifacts/
├── baseline-ablation/
├── coupling-energy/
├── validity-envelopes/
├── controlled-transients/
│   ├── screen.csv
│   ├── restart_states.csv
│   ├── selected_cases.csv
│   ├── validation_summary.csv
│   └── selected-cases/
├── provenance/
├── summary.json
└── summary.md
```

The screen table is retained for reproducibility, but it is not the headline
paper result. The selected validated cases, equation-derived envelopes, baseline
ablation, and coupling-energy decomposition are the scientific outputs.

## Current baseline interpretation motivating the redesign

The v1.1.2 canonical run immediately before this redesign was healthy and
revealed an important scale separation:

- the largest actuator corrections occur during the initial rigid
  engagement/capture transient;
- after approximately 0.10 s, the primary flyweight dynamic correction is
  extremely small in the ordinary launch;
- the secondary helix retains a small but measurable continuous correction;
- independently integrated quasi-static variants remain close to the full
  baseline trajectory;
- the secondary helix contributes a large raw generalized shift-inertia term,
  demonstrating why raw `M_ss` magnitude alone cannot be used as a trajectory
  consequence metric.

Those observations motivate reporting the engagement/capture transient
separately and replacing arbitrary hardware scaling by the exact \(\Pi\)
validity measures above.
