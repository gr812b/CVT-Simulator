# Belt publication evidence — 28 September 2026

This records the retained evidence and current combined main figure for Results 4.4.3.
No simulations were rerun for the revised figures/prose. The 419d33d draft was
rejected; see the manuscript unit's TARGET_AND_REVIEW.md and REVIEW_FINAL.md
for the active presentation. Earlier review files record superseded drafts.
It supersedes the pending refinement/R2 status in the historical `BELT_REVIEW.md`.
The manuscript remains a draft for author review. No independent reviewer was used.

## Exact sources and scope

- Original run/delivery base: `377cb34d8089e15fd1d7893fbad8aceeb5e78c28`.
- Recovered local baseline: `b9051a25ed58193584208b9139ac346bcd08e23a`.
- Previously checked integration baseline: `results-finale` at
  `16361b7315c98f926464232f07aaf3695ab92e9d`. No new remote check is claimed.
  The later abstract and figure-path edits are preserved, not redrafted.
- Task branch: `codex/belt-agreed-spine-2026-09-28`.
- Mechanics: `cinder-cvt==1.1.2`, tag commit
  `7637a38b4fb9ec21dfb953c1c80a27ec5f389654`.
- Installed CINDER source: all 132 Python files match that tag byte-for-byte;
  file hashes are in `publication_inputs/runtime_source_check.json`.
- Python 3.12.14, NumPy 2.5.2, SciPy 1.18.1, Matplotlib 3.11.1.
  The release environment imports installed CINDER, never `cvtModel/src`.
- Original discovery ZIP: `artifacts(20260916-222846).zip`, 60,247,504 bytes,
  SHA256 `9bacf2c5e8df301aa1e1a8bc080de1798222d749e7d338bf5331447da16a98cb`.
  Its earlier audit covers 62 completed cases and six isolated-row failures.
- Exact selected archived case/protocol documents were copied without editing
  into `publication_inputs/cases`. `selected_sources.json` records the original
  archive member names and hashes. Numerical settings are changed only when
  a run is instantiated; each run saves its actual effective input.
- Reference bilateral secondary-helix policy comes from the release-scoped
  `defaults/reference_model/slotted_helix.py` (via `reference_case.py`), as in the previous Results studies.
  This is not the newer simulator's unilateral topology.

The 42 selected runs comprise 11 full cases, seven joint-omission cases and
three 3%-density cases, each at two numerical settings. `run_plan.json` is the
exact plan; Appendix D.8 lists the physical inputs. The original broad sweep
was not rerun. LSODA settings are `(rtol, atol, max_step_s)`:
`nominal=(1e-6,1e-9,0.01)` and `tight=(1e-7,1e-10,0.005)`.
“Nominal” is an internal file label, not a preferred production tolerance.

## Reproduce from the repository root

Create the release environment when needed:

```sh
python3.12 results/cinder-v1.1.2/bootstrap.py
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/verify_environment.py
```

Plot the supplied compact evidence without any integration:

```sh
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/reduced-belt-transients/run.py --publication plot
```

This writes main belt_load_rate and supporting belt_shift_transient,
belt_coefficient_driver and belt_density_response as PDF, PNG and SVG into
`docs/CVT_Module_Formulation/figures/results/dynamics`. The four plots have
12 exports; `figure_hashes.json` records them. Main Figure 4.13 combines the
applied grade, shift speed, dimensional radial force and signed instantaneous
percentages for the fast case. Its caption retains the three integrated shares.

For a clean-directory reproduction, append
`--publication-figure-dir /absolute/path/to/clean-figures`.
The compact evidence already contains the envelope case and five-term regional
shares over explicit engaged windows. The current presentation edit leaves those
inputs, raw runs and numerical model comparisons unchanged. Regional integrals
accumulate separately within continuous segments. The five-term symbols and
colours remain consistent. Retired belt_balance_shares, belt_load_rate_forces
and belt_tension_response exports are removed from the active folder.
`provenance/check_reader_figures.py` verifies the plotted masks, signed
comparisons and event/refinement qualifications from that compact evidence.

To reconstruct the compact evidence from supplied raw outputs, extract the
separate `CINDER_4_4_3_Raw_Runs_2026-09-28.zip` at the repository root. It puts
the 42 run directories under this study's `artifacts/publication/`.
Then run:

```sh
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/reduced-belt-transients/run.py --publication prepare
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/reduced-belt-transients/run.py --publication check
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/reduced-belt-transients/run.py --publication plot
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/reduced-belt-transients/run.py --tests-only
```

`check` explicitly reports the number of raw files verified. If the raw
publication directory is absent, it checks compact-input/source hashes and the
stored numerical audit, and reports zero raw files; that is not a raw-data check.
A partial raw directory is an error.

Only if reintegration is wanted:

```sh
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/reduced-belt-transients/run.py --publication run --publication-case all
```

Existing run payloads are hash-checked and reused. To force new integrations,
use a new `--publication-dir /absolute/path/to/new-runs` on `run`, `prepare`
and `check`. `prepare` replaces the compact publication inputs; preserve the
committed inputs when comparing a new environment. Individual jobs accept
`--publication-case flat --publication-variant omission --publication-level tight`.
Independent subprocesses isolate the temporary equation hook. The publication
route does not enter the old discovery route's output-directory replacement.

## What was actually reduced

With `q=rho_b A_b`, the full wrap offsets are
`C=q(v_b^2-r*r'*sddot-r*r''*sdot^2)` and
`A=q(r*vdot+r'*sdot*v_b)`. The joint omission removes the `r*r''*sdot^2`
and `r'*sdot*v_b` biases from **both** wraps before equation assembly.
The acceleration gains remain. All other mechanics, belt mass, radius
kinematics, sticking constraints, contact laws and reset laws remain.
`experiments/publication.py:omit_two_terms` restores the frozen functions on
exit; the installed package files are never changed.

`wrap_audit` reconstructs local tension and normal loading with the same full
or reduced offsets. Extrema occur at each wrap's endpoints for the analytical
exponential/linear solution, so positivity is not inferred from a positive
integrated normal load. The endpoint-sum difference is checked against the
assembled tension residual. This is an approximation of the continuous
belt equations, not a newly derived impact law. No new energy-conservation
claim is made for the reduced model; the comparison concerns motion, event
sequence and the recorded mechanical/contact checks.

The separate density experiment scales both global and local inertia through
one assembly density change. It retains finite density (3%); zero density was
not run. The archived row-only modification scales just the global transport
coefficient while leaving wrap inertia unchanged. Its six failures occur at
the same engagement before the later load programmes differ.

## Event handling, masks and numerical meaning

Every run retains `native.npz`, dense `states.csv.gz`, mechanical `terms.csv.gz`,
`segments.json`, exact incoming/outgoing `events.json`, `inspection_errors.json`,
the effective input/protocol and `summary.json`. There are 378 hashed payload
files. Native arrays include boundary/host state, not just the five CVT states.

State grids use 1 ms spacing, 50 microseconds through early reference engagement,
and 250 microseconds around forcing. Mechanical grids include every native
accepted state, every segment endpoint, 5 ms background sampling, 250 microseconds
through the first 0.15 s and 1 ms around forcing. Delayed weakened-actuator
engagement is also resolved by adaptive native samples and exact event sides.
No interpolation crosses a continuous-segment boundary. Both time limits are
retained when model event times differ. Integrals are accumulated within
segments; primary-disengaged states are excluded from engaged wrap diagnostics.

Maximum shift differences compare common physical times and include both
limits. Matched event times, incoming/outgoing states, ordered events/modes and
same-mode comparisons are saved separately. A brief pointwise velocity mismatch
caused by different reset times is not called a sustained motion change.

- All 42 runs completed; no state inspection failed.
- Minimum saved local normal loading: 0.525931464 N/rad; tension positive.
- Maximum sticking speed mismatch: 0.0112595 mm/s.
- Maximum eight-row residual: 4.26098e-10 in its force/torque unit.
- Reconstructed endpoint-sum residual agrees within 1e-8 N.
- All seven full/omission pairs have identical event and mode order at both
  settings. At tighter settings the largest shift difference is 0.016334 um;
  the largest event-time difference is 0.829157 us. Individual refinement
  changes reach 0.213470 um. The tiny omission differences lie below those
  changes and are not assigned nanometre physical precision.
- At 3% density the maximum shift change is 0.0699113 mm (0.422% of engaged
  travel), and primary speed changes by at most 8.33458 rpm. Each lighter-belt
  run has one additional early contact–seat return at both numerical settings.
  Later event order agrees. A claim of unchanged complete event sequence would
  be false.

These checks cover saved states and analytical wrap extrema at those states,
not a continuous-domain proof. The wider discovery archive reaches both-slip
and primary-slip/secondary-stick; the opposite mixed branch was not realized.

## Corrections to historical evidence

R1's old printed percentages were 100 times too large. Recalculated historical
five-state nRMSE at 3% density is 0.834798%, 0.814227%, 0.855810% for
flat/loading/unloading (shift speed in all three). That historical metric
collapses duplicate event times; it is not the final hybrid error measure.
The publication replaces it with the dimensional/event-aware comparisons above.

R2 is now an executed joint-omission comparison, with the numerical qualification
above. It is no longer an unrun task or a deleted presentation placeholder.
The refined later-travel radial activity is 21.2%, not the discovery 24.3%;
strong overrun is 14.9%, not 17.1%. Mild overrun has a sampled curvature share
of 19.2% at only -0.739 mN, but a 0.363% integrated transition share. That
sample is not advertised as a converged peak. Do not transfer a contact-case
percentage to overrun or equate any equation share with a motion error.

## New regional comparisons and interpretation

The five-part balance is restored to the main text, derived from the existing
capstan limit and local radial/tangential equations. The common centrifugal
contribution cancels only in the endpoint-sum subtraction, not in local loading.
Each regional share is `100*integral(abs(F_i))/sum(integral(abs(F_k)))`.

- Free shift: 0.957246091683–5 s, tight flat full. Normal loading 49.7582%,
  belt acceleration 49.6819%, shift acceleration 0.47445%, curvature 0.02834%,
  moving radius 0.05712%.
- Early engagement: first contact 0.061971867086 s through last early seat
  return 0.066012453508 s, engaged pieces only. Shift acceleration 49.9877%,
  belt acceleration 39.2514%, normal loading 10.7324%, curvature 0.01627%,
  moving radius 0.01233%.
- Mid-shift load: 2.4875–2.543364356904 s, tight envelope full. Shift
  acceleration 21.2346%, belt acceleration 41.4683%, normal loading 37.2525%,
  curvature 0.01238%, moving radius 0.03221%.
- Largest regional-share refinement change: below 0.002 percentage points.
- Entire mid-shift figure window (−20 to +120 ms): free stick–stick; five
  signed contributions sum within 5.991e-13 N. The belt-acceleration term
  changes sign, so the prose does not call it negative throughout the rise.
- Combined-tune support window: moving-radius peak 7.07504 mN, hence 7.1 mN,
  correcting the preceding text's 7.2 mN. Complete-run delayed engagement is
  a different window and is not substituted for that later-return peak.

The percentages are contributions to a small difference of two wrap tension
sums, not fractions of gross clamp force or errors caused by a reduction.
Tune scalings are called tune changes, not an expanded hardware comparison.

## Runner provenance

Every `summary.json` records the runner hash used for its integration.
`provenance/pilot_runner.py` preserves the exact module used for the first
`flat_nominal_full` run (SHA256
`18cdcc1c1fd8685ed92e4711bb08d46a20610f7843b2dc9f52ad671c369284b7`).
`provenance/batch_runner.py` preserves the exact module used for the remaining
runs (SHA256 `42175c691bd73e947daffea5db0fea924b54419479a3d19c4ff1db6794d32649`).
The batch module adds independent-process orchestration; the numerical run,
reduction and audit functions are identical. The maintained version further
makes a failed batch return a nonzero exit status. These orchestration-only
changes do not warrant reintegrating verified outputs.

## Manuscript integration and build

`docs/CVT_Module_Formulation/results-finalization/belt-4-4-3/section.tex`
and `appendix.tex` are the source fragments. The same directory contains
`integrate.py`, `build_preview.py`, the figure register and review/continuation.
Run from the repository root:

```sh
python3 docs/CVT_Module_Formulation/results-finalization/belt-4-4-3/integrate.py --check
python3 docs/CVT_Module_Formulation/results-finalization/belt-4-4-3/build_preview.py --output-dir /absolute/path/to/preview
```

The preview needs a normal LaTeX installation including `siunitx`, and reuses
the maintained secondary unit's preview helpers. In this environment the
existing local siunitx 3.3.7 tree was supplied through `TEXINPUTS` because the
system package was absent. The five-page reading and six-page support compile
with the source preamble, manuscript width and actual equation/figure labels.
The preliminary full-source pass resolves numbering with graphics/bibliography
suppressed; it is not a full-book layout build. The unchanged 4.5 integration
conflicts (M150/M170 and restored cyclic teaser) remain separate tasks.


## Main-text moving-state evidence (28 September 2026)

The final explanatory revision adds five windows from the existing nominal and
tight full runs. Three cover the complete unloading, combined-tune and strong
resisting-torque rises. Two cover actual reversed power from 2.25 s to the first
upper-stop capture. All are free, stick–stick intervals. Both contact traction
signs and boundary-power signs are checked in the reversed-power rows. Integrals
are formed within segments; the incoming capture side is retained.

From the repository root, replay the compact evidence without simulations:

```sh
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/reduced-belt-transients/analysis/moving_state_evidence.py --output /absolute/path/to/moving_state_audit.json
```

The default input is publication_inputs/belt_moving_state_samples.npz; the
committed result is belt_moving_state_audit.json in the same directory. To recreate
the compact samples from the separate retained raw archive, add
`--prepare-from-raw`. This verifies eight unique source-force hashes against the
unchanged belt_publication_audit.json before extraction. No frozen core input,
force export, case, model or integration is changed by this addition.

The replay checks the curvature force against coefficient times squared speed,
reconstructs both simultaneous moving-radius wrap parts, and compares each share
at both numerical settings. The largest small-term share change is
2.839e-6 percentage points. Net loop cancellation does not by itself justify
omitting the local terms; the separate full/omission integrations provide that
motion comparison. Main-table interval shares must not be interpreted as
instantaneous maxima or percentages of gross clamping.
