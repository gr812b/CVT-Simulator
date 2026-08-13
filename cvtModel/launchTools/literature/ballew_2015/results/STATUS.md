# Current Ballew benchmark status

The canonical Ballew reconstruction uses A10 to translate the published node-level Coulomb
coefficients into CINDER's reduced traction-utilization convention. The first A10 runs exposed a
separate CINDER hybrid-boundary implementation bug; that bug is now diagnosed and corrected
without changing CINDER's force laws or any Ballew parameter. See `../SINGULARITY_DIAGNOSIS.md`.

## Superseded v9 early terminations

The v9 corrected force replay terminated near `0.032252 s`, and the source-constrained controller
case near `0.0172 s`, with a singular free engaged closure. Instrumentation showed that LSODA had
stepped slightly outside the low-ratio boundary while bracketing its event. CINDER projected the
trial geometry to `s = 0`, but the geometry accessor supplied the deadzone-side derivatives there.
For Ballew's zero-width deadzone and zero moving-sheave masses that removed the entire `s_ddot`
column and made the 8x8 matrix exactly rank seven.

Those terminations are **not physical/model-comparison results**. Preserve them only as provenance
of the now-resolved implementation defect.

## Boundary correction

Engaged snapshots now use explicit engaged-side one-sided geometry derivatives at the engagement
boundary; the separate deadzone snapshot retains the deadzone-side derivatives. At the exact
previously failing trial state this restores matrix rank from 7 to 8 and removes the pure-`s_ddot`
null direction.

After the correction:

- the force-replay case crosses its former `~0.032252 s` failure and has been stress-integrated to at
  least `1.0 s` under the benchmark tolerances;
- the reconstructed-controller case crosses its former `~0.0172 s` failure and has also been
  integrated to at least `1.0 s`;
- focused one-sided-geometry, zero-width-deadzone, and contact-switch tests pass.

The canonical five-second output folders should therefore be regenerated from the corrected code.

## Controller reconstruction

Ballew publishes `Kff=1.2`, `Kp=5`, `Ki=75`, a fixed `2000 N` secondary clamp, and a fixed-input-
speed objective initialized at `2500 rpm`. The thesis does not publish the complete controller
algebra, feed-forward operand, initial integral/bias, or saturation/anti-windup.

The offset-free Figure 41/45 audit strongly favors `e = primary_rpm - 2500` with error in RPM. The
source-constrained headline controller remains

`Fp = 1.2*(2000 N) + 5*e + 75*integral(e dt)`,

with zero initial integral and no unpublished saturation/anti-windup. The feed-forward operand is an
explicit reconstruction assumption, not a published equation.

## Historical raw-mu replay

`legacy_raw_mu_replay/` preserves the first five-second replay only as historical provenance. It used
the pre-A10 convention mismatch (`0.55/0.40` copied directly into CINDER lambda limits) and is not
canonical.

## Contact-transition / unilateral-reaction correction

The first post-v10 five-second closed-loop run revealed another non-physical trapping mechanism:
a contact re-stick while sitting on the low-ratio seat could make the recovered seat reaction jump
from compressive to tensile. Because the release event only watched for a continuous zero crossing
within the old contact topology, the successor segment could begin with a seat that would have to
pull and remain trapped there.

The transition resolver now rechecks unilateral reaction admissibility immediately after every
contact-topology change at a low-ratio seat or upper stop. If the successor contact branch requires a
tensile stop reaction, the stop releases at the same event time. This is hybrid bookkeeping only; no
CVT physical equation or Ballew parameter is changed.

The canonical v11 full runs are generated only after both boundary corrections.


## Canonical full five-second results after both hybrid corrections

The canonical A10 force replay and A11 closed-loop controller cases now both reach `t = 5 s` under
LSODA with `rtol=1e-7`, `atol=1e-9`, and `max_step=1e-3 s`. These runs use unchanged CINDER
physical equations. The only core changes relative to the first A10 attempt are the two hybrid
boundary/admissibility corrections documented above.

### Force replay

`results/force_replay/` replays digitized Figure 45 into CINDER. It completes in 252 segments with
251 transitions. Figure 41 comparison errors are:

- primary RPM RMSE: `1796.106 rpm` (`71.880%` of reference mean);
- secondary RPM RMSE: `38.255 rpm` (`3.187%`);
- speed-ratio RMSE: `1.451341` (`69.606%`).

Thus the corrected friction convention does not remove the large primary/ratio disagreement under
identical clamp forcing.

### Closed-loop controller portability

`results/closed_loop/` applies the source-constrained A11 controller to unchanged CINDER and treats
Figure 45 as an output. It completes in 1630 segments with 1629 transitions. Errors are:

- primary RPM RMSE: `109.665 rpm` (`4.389%`);
- secondary RPM RMSE: `32.922 rpm` (`2.743%`);
- speed-ratio RMSE: `0.109299` (`5.242%`);
- primary-force RMSE: `1180.228 N` (`46.036%`).

The speed/ratio agreement is therefore much better in closed loop, but it is achieved with a very
different clamp-force history and extreme shift/contact chatter. This should be interpreted as a plant
model difference exposed by the controller, not as validation of identical internal mechanics. A
numerical convergence study of the chatter is the next recommended benchmark step before placing
weight on its exact frequency or pointwise force error.
