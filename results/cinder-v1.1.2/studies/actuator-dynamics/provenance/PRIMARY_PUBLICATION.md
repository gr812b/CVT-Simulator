# Primary publication evidence — 25 September 2026

This record supports Results 4.4.1 only. It closes the primary evidence gap P1;
it does not settle secondary S1 or belt R1/R2.

## Source and model identity

All new integrations use the installed PyPI `cinder-cvt==1.1.2`, corresponding
to tag commit `7637a38b4fb9ec21dfb953c1c80a27ec5f389654`. The canonical entry
point verifies Python 3.12, NumPy 2.5.2, SciPy 1.18.1 and Matplotlib 3.11.1,
rejects an editable/direct CINDER install, and rejects the live simulator
source on the import path. The study helper and release-local defaults are
retained with this commit. The simulator itself is not modified.

The full primary uses the fixed-pivot flyweight law, including both pivot
terms and changing shaft-axis inertia. The reduced primary keeps the same
centrifugal law, spring and translating mass, removes both pivot terms, and
holds total primary shaft inertia at its initial 0.00491861 kg m². The
secondary remains dynamic. Thus a reintegrated full/QS difference measures
the combined primary reduction, not the axial terms in isolation. The signed
shaft correction is separately reported in D.7 and the numerical audit.

## Recovered outputs and the current reference assembly

The original September 10 archives are:

| Archive | SHA256 | Use |
|---|---|---|
| `artifacts(2).zip` | `b8fce02a6833f5947b428d3c9df0c6a902a0c59f2cb4745df17004e3b748d6e9` | Baseline, 72 primary screen rows, selected full/QS stress/control traces and exact restart states. |
| `artifacts(4).zip` | `ffec0a4a96a09049e9a6ad90247776e484740cc8471260242417b621dd32c479` | Independent archive copy of seven byte-identical baseline CSVs; additional component reports. |

Their manifests identify the 1.1.2 release. `PRIMARY_EVIDENCE_AUDIT.json` in
the manuscript unit records the initial recovery/reconstruction. It is a
historical audit; `publication_inputs/primary_publication_audit.json` records
the new publication runs. Archive 4 has no controlled-transient outputs.

The archived study used an earlier one-sided helix admissibility guard;
the maintained assembly uses the documented bilateral reference fixture.
The signed helix force law is unchanged. The recovered primary screen is
reused as an identified historical screen, not claimed as a newly run sweep.
The new nominal full baseline reproduces its initial outgoing force to
floating-point precision and its event times within about 2.1e-8 s. The
selected full/QS response metrics also reproduce at their reported precision.
The baseline and selected refinement plots themselves use the new current
reference-assembly runs. No secondary-topology comparison is inferred here.

The old selector's requested 1/5/10/20% targets were not achieved. These labels
are not carried into the figures. Each plotted screen point is the largest
**achieved sampled** correction among the six signed amplitudes at that
travel and rise time. The current schema-4 selector corrects the target policy.
The old `time_to_full_shift_s` metric means within 0.20 mm of maximum travel;
it is not a stop-event time and is not used in this section.

## New runs and output handling

`publication_inputs/primary_publication.json` records every selected input.
Twelve integrations were completed: four baseline runs (full/QS, nominal/tight)
and eight selected-ramp continuations (full/QS, nominal/tight, forced/control).
The selected initial physical vectors are copied exactly from the archived
first rows, retaining the original free stick-stick mode. They are separately
conditioned model states, not a shared state. Each model's own unforced
control is subtracted before comparing responses. Rebasing the host angle
changes distance metadata only under the time-programmed flat-road boundary.

Baseline nominal/tight settings are `(rtol, atol, max_step)` =
`(1e-4, 1e-7, 0.01 s)` and `(1e-5, 1e-8, 0.001 s)`. The selected ramp uses
the same tolerances with max step 0.000625 s at both levels. Extra output
sampling does not change the integration: baseline 1 ms plus 25 µs near
engagement, selected continuation 0.1 ms. Each baseline segment keeps both
exact endpoints. The plotted capture is a marked jump, not interpolated
continuous motion. Response interpolation is permitted only after checking
that all selected continuations contain zero events.

Raw exports under `artifacts/primary-publication/` retain trajectories,
force contributions, events, summaries and per-run provenance. Their full
hash list is committed in the publication audit; raw bytes are also in the
delivery ZIP. `source_sha256` in the original run provenance is an export-time
snapshot. During the first baseline exports the runner's unused transient
initial-mode branch was corrected; baseline execution and its scientific
dependencies were unchanged. All successful transient runs use the corrected
archived-mode continuation. No failed initialization produced a plotted run.

The compact NPZ is committed and verified before plotting. It retains the
arrays used in both figures, including segment identities, exact first-event
sides, signed budgets, response/control differences and sweep values. The
algebra/force audit uses the actual reference sheave half-angle and translating
mass, rather than a guessed geometry. The JSON audit records every mask and
metric through the generating code and the raw hashes; it does not claim a
new comprehensive local-wrap/contact verification of the whole screen.

## Findings and limits relevant to reproduction

- Tight full/QS first engagement: 61.97135/60.04125 ms and
  565.163/673.331 mm/s approach speed. The approximately 6 µs timing change
  under refinement is small compared with the 1.93010 ms model difference.
- First outgoing full-state budget: +1404.352 N centrifugal, −1234.675 N
  spring, +74.832 N pivot correction, giving 244.509 N actuator force.
  The same-state QS actuator force is 169.677 N. These are post-capture
  continuous forces before belt reaction, not capture impulses.
- From 0.1–10 s the sampled maximum correction is 0.0450 N, and the
  maximum simultaneous centrifugal fraction is 0.00147132%.
- Original screen maximum: 0.0506995%. The densely sampled selected
  −20 N m / 5 ms mid-travel case reaches −1.83099 N, or 0.0509660%,
  against 3592.58 N centrifugal force. The post-onset denominator stays
  above 2995 N. These are sampled results, not continuous-time bounds.
- The selected full forced-minus-control shift response reaches 0.82265 mm.
  Maximum paired QS-minus-full response differences are 2.52652 µm and
  0.670415 rpm. Tightening tolerances changes the entire difference curves
  by at most 0.00440 µm and 0.000301 rpm. The tiny difference is numerically
  resolved in this check; it is not promoted to a large practical effect.
- Sampled free-primary axial-balance residuals are below 4.1e-12 N. Sampled
  normal resultants stay positive and stick-stick tractions remain within
  the static limits. D.7 gives the signed shaft-inertia diagnostic separately.
- The later tiny seating sequence is not invariant: QS records 14/16
  transitions at nominal/tight settings; full records 16/16. The first
  engagement and smooth event-free torque response support the main claims;
  no converged rebound-count claim is made.

The screen, refinement and internal model comparison do not establish
experimental accuracy or universal validity of a quasi-static primary.

## Reproduction

From the repository root, with the frozen environment installed:

```sh
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/actuator-dynamics/run.py --plot-only
```

This verifies the environment and compact input hash, then writes the two
PDF/PNG figures and `primary_figure_manifest.json` under
`docs/CVT_Module_Formulation/figures/results/dynamics/`. Use `--figure-dir`
to choose a separate directory. This command does not integrate or delete
existing artifacts.

```sh
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/actuator-dynamics/run.py --primary-publication
```

This repeats the twelve focused integrations, derives the compact inputs/audit,
and regenerates the figures. It preserves other study artifacts and reuses
the explicitly frozen 72-row screen. It does not silently rerun or replace
the historical screen with the newer selection policy. The raw-to-compact
step can also be run separately with `analysis/prepare_primary_publication.py
--raw-dir PATH`.
