# Ballew 2015 reconstruction contract

This document is the normative reconstruction contract for the Ballew study.
It records every important bridge required because Ballew and CINDER do not use
identical coordinates, force normalizations, inertia ownership, or controller
representations.

The benchmark is a **model-to-model comparison** against Ballew's Chapter 5
simulated vehicle-acceleration case. Figure 41 and Figure 45 are Ballew
simulation outputs, not experimental validation data. No CINDER physical
parameter or controller gain is fitted to those traces.

## Source-native quantities retained

The source values used by the study are:

| Quantity | Value |
|---|---:|
| sheave half-angle | 15 deg |
| pulley center distance | 0.2421 m |
| input radius limits | 0.0159–0.0838 m |
| output radius limits | 0.0159–0.0838 m |
| input pulley + engine inertia | 0.008 kg m² |
| output pulley inertia | 0.002 kg m² |
| output pulley + ATV inertia | 1.275 kg m² |
| 1-D belt length | 0.8636 m |
| belt mass | 1.000 kg |
| static friction coefficient | 0.55 |
| kinetic friction coefficient | 0.40 |
| Ballew near-zero velocity threshold | 0.02 m/s |
| fixed output-to-wheel reduction | 8.93 |
| ATV mass | 226 kg |
| frontal area | 1.39 m² |
| tire radius | 0.317 m |
| aerodynamic drag coefficient | 1.0 |
| rolling-resistance coefficient | 0.048 |
| simulated interval | 5 s |
| initial input speed | 2500 rpm |
| initial output speed | 1136 rpm |
| initial ratio printed by Ballew | 2.2 (rounded description) |
| input torque | 18 N m |
| secondary axial force | 2000 N |
| controller Kff | 1.2 |
| controller Kp | 5 |
| controller Ki | 75 |
| reference nodal time step | 1e-5 s |
| node count | 50 |

Ballew reports the material-test belt as a Gates G-Force `26C3596`.

## A1 — inertia ownership and vehicle boundary

Ballew publishes a combined input-pulley/engine inertia rather than a split.
The full `0.008 kg m²` is therefore placed at CINDER's primary shaft boundary
and is not duplicated in the CVT-owned inertia set.

Ballew also publishes `1.275 kg m²` for the output pulley + ATV system. The
reconstruction uses his `8.93` transmission ratio as the fixed CVT-output to
wheel reduction for the simulated vehicle boundary. CINDER separately owns the
published `0.002 kg m²` output-pulley inertia and the vehicle translation is
reflected through the fixed reduction. The remaining inertia is carried as the
direct secondary-boundary inertia so the published total is preserved.

This is an explicit reconstruction bridge, not a fitted parameter.

## A2 — unreported road constants

Ballew gives vehicle mass, tire radius, frontal area, Cd and rolling resistance,
but does not report every environmental/numerical constant needed by the CINDER
road-load implementation. The study therefore makes the following explicit reconstruction choices:

- air density: `1.225 kg/m³`;
- gravity: `9.80665 m/s²`;
- rolling-speed regularization: `0.01 m/s`.

These values are reconstruction assumptions and are kept visible in the
resolved study output.

## A3 — exact initial state

Table B1's two explicitly tabulated shaft speeds are authoritative:

- primary: `2500 rpm`;
- secondary: `1136 rpm`.

Their exact ratio is about `2.200704`, so the separately printed `2.2` is
interpreted as rounded. The initial shift coordinate is solved from the exact
shaft-speed ratio and reconstructed belt geometry. Initial shift rate is zero.
The belt transport speed is the compatible no-slip line speed at that shift.

## A4 — equivalent belt mapping

Ballew's transient formulation is a 1-D nodal belt model. CINDER requires a
smooth belt cross-section and distinguishes the outer surface from the cord-line
effective path.

The benchmark therefore uses Ballew Figure 39's minimum smooth trapezoidal
section as an **equivalent load-carrying core**, not as a claim about the literal
cogged belt envelope:

- height: `0.30 in`;
- outer/top width: `1.18 in`;
- inner/bottom width: `1.05 in`;
- cord depth: `0.05 in` inward from the outer surface.

Ballew's `0.8636 m` nodal length is identified with the CINDER effective/cord
line. The CINDER outer length is offset by `2*pi*d_cord`. An effective density is
then chosen from `m = rho A L_outer` so the CINDER belt mass is exactly Ballew's
published `1.000 kg`. That density is a mass-preserving model parameter, not a
measured rubber density.

The simultaneous listed minimum radii are not used as a geometrically closed
endpoint. At low ratio the secondary is set to its published maximum radius and
the compatible primary radius is solved from Ballew's belt length and center
distance. Maximum shift is chosen so the primary reaches its published maximum
radius.

## A5 — always-engaged topology and clamp balance

Ballew's Chapter 5 case has no primary disengagement interval. The CINDER case
therefore has `deadzone_shift = 0`: an always-engaged, zero-width deadzone whose
lower boundary is the engaged low-ratio seat.

Ballew does not integrate a movable-sheave axial equation of motion. Instead he
searches radial position until the summed belt axial reaction equals the applied
clamp. Both literal moving-sheave masses are therefore zero in the benchmark,
which makes the local CINDER axial rows algebraic clamp-force balances. This does
**not** make CINDER's global shift coordinate equivalent to Ballew's distributed
radial migration; the difference is deliberately retained as part of the
model-to-model comparison.

The 1 kg belt remains dynamically active in CINDER through the reduced closed
belt equations.

## A6/A7 — digitized Figure 41 and Figure 45 data

The exact WebPlotDigitizer project files, raw exports, prepared CSVs, and source
thesis are stored directly under `reference/`. The benchmark-ready CSVs are
regenerated deterministically by `reference/prepare_reference_data.py`.

Preparation of Figure 45 is deliberately minimal:

1. add explicit headers;
2. preserve Figure 41's two native point grids independently;
3. average four exact duplicate Figure 45 time coordinates created by clicking
   near-vertical segments twice in the same pixel column;
4. prepend the first visible Figure 45 force to `t=0` using a zero-order hold,
   because the published curve starts at about `0.095541 s` but force replay
   requires an input at the initial state.

No smoothing, filtering, curve fitting or resampling is applied. Figure 41 error
metrics are evaluated at each trace's native digitized timestamps. A derived
speed-ratio comparison uses the sorted union of those native time sets over the
common visible interval and linearly interpolates only the opposite reference
trace.

Figure 45 has two distinct roles:

- force replay: prescribed primary clamp input;
- closed loop: output reference only.

## A8 — distributed belt initial tension cannot be reproduced exactly

Ballew's distributed nodal belt has internal longitudinal states and can define
an initial zero-longitudinal-tension configuration in a way CINDER's reduced
belt representation cannot reproduce identically. The benchmark preserves the
CINDER model form rather than adding a fitted initial hidden state.

## A9 — vehicle load is not a fixed brake torque

The secondary shaft torque is generated by Ballew's simulated ATV/road-load
reconstruction. It is not replaced by a constant output torque. This is
important because the benchmark is the complete simulated vehicle-acceleration
case.

## A10 — friction convention translation

Ballew's `mu_s=0.55` and `mu_k=0.40` multiply each node's axial sheave-compression
reaction `F_Z`, and Ballew's axial search enforces the summed node reaction
`sum(F_Z) = F_clamp`. His gross tangential capacity is therefore

`Q_max = mu F_clamp`.

CINDER 1.0.0 uses a different normal-force convention. Its reduced contact law
uses `Q = lambda N`, where `N` is the **physical integrated normal load over both
sheave faces**. With equal face-load sharing, the zero-moving-sheave-mass axial
balance used by this benchmark is

`F_clamp - N cos(beta)/2 = 0`,

so

`N = 2 F_clamp / cos(beta)`.

To preserve Ballew's gross tangential capacity rather than blindly copy numbers
between the two normal-force definitions,

`lambda N = mu F_clamp`,

which gives the CINDER 1.0.0 translation

`lambda = mu cos(beta) / 2`.

The benchmark derives these values directly from Ballew's published `mu` values
and published `beta = 15 deg`; they are not independently entered constants. At
`beta = 15 deg` this gives approximately:

- static CINDER traction limit: `0.26562960222949383`;
- kinetic CINDER traction magnitude: `0.19318516525781368`.

The earlier Ballew-study bridge `lambda = mu/(2 tan(beta))` belonged to CINDER's
pre-PR471 normal-force convention and must not be used with the released 1.0.0
axial balance.

This is a convention bridge, not a friction fit and not a claim that CINDER's
single reduced contact interface reproduces Ballew's 2-D node friction field.

## A11 — reconstructed PI + feed-forward controller

Ballew publishes `Kff=1.2`, `Kp=5`, `Ki=75` and the 2500-rpm objective but not a
complete executable controller equation. The source-constrained reconstruction
uses:

- `e = primary_rpm - 2500`;
- `Fff = 1.2 * 2000 = 2400 N`;
- zero initial error integral;
- no added saturation;
- no added anti-windup.

The integral is a proper host ODE state. A small bridge exposes that state to the
study-local custom primary force law; it is not accumulated imperatively and no
state is added to CINDER's physical five-state CVT model.

## Near-zero contact behavior

Ballew's node friction has a finite near-zero layer: kinetic Coulomb friction for
`|v_rel| >= 0.02 m/s`, and a static/impending-motion rule below that threshold.
CINDER does not silently copy this threshold into its gross pulley-contact hybrid
switching tolerances. The benchmark retains CINDER's normal contact
mode graph and treats any remaining difference as model-form difference unless a
separate sensitivity study explicitly changes that assumption.
