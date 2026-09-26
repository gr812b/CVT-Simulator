# Section 4.2.2 — evidence, figure and execution identity

## 24 September revision after author feedback

No simulation was repeated. The exact run below still supplies all evidence.
The revised plot is 6.5 by 4.6 inches: separate signed primary/secondary work
and kinetic-energy increase replace the rejected totals overlay in (a);
(b) retains the signed remainder; (c) directly labels nominal/tighter lines;
(d) uses the actual maximum power-evaluation interval, halved to the right.
The values export now includes the complete unrounded final energy ledger.

The manuscript starts from the energy question and explains the chosen test,
then explains sliding loss from unequal contact speeds under equal-and-opposite
traction and capture loss from arrested motion. The event detail locates the
fast remainder change in continuous motion; the exact event sides establish
zero jump, rather than visual overlap alone. The rejected magnitude-based
capture rationale and Assumption 15 ending are removed. Both three-page
readings build without reference or box warnings. All pages were inspected;
the four publication exports reproduce byte-for-byte, and three integrity
regressions pass. These are self-review and reproduction results, not author
acceptance or independent scientific validation.

The active source SHA is
`51c1ac97f56caa48df18a27f2059e4d0841a80c132a8eb20da9c1bc96d297a76`.
Integration preserves the supplied 4.2/4.2.1 and all other main text. In addition
to D.2, its missing B.5 numerical-seating dependency is explicitly included.
See `results-finalization/rebuild-4-2-2/` for the complete brief, alternatives,
review and instructions. The delivery and figure register identify the commit.

## Historical execution and first publication record

Ready for author review, not author accepted. One complete canonical execution
on 23 September 2026; no second simulation was needed for figure revisions.
Code/assets commit: `83b2c31e690dab9d052c91308f551432ad9e0349`.

## Exact source and protocol

- Repository parent before this unit: `61975ad384a5e67b69808ac0ed2f7b6ffd4b930a`,
  preserving completed Section 4.2.1. Task branch: `results-finalize-4-2-2`.
- Remote `results-latex` remained at the handoff revision
  `5c616eb19775ddb899020153c3869e6972c092ec` when checked at startup.
- Mechanics: installed `cinder-cvt==1.1.2`, tag `cinder-v1.1.2`, source commit
  `7637a38b4fb9ec21dfb953c1c80a27ec5f389654`. The live source was not imported.
- Run identity: `energy-consistency-63428236f0140f5c`. Exact 18 executed input
  snapshots and 11 numeric output hashes are recorded in
  `execution_2026-09-23.json`; raw outputs and snapshots travel in the delivery
  archive under `evidence/artifacts/`. The parent commit is not claimed to
  contain the subsequently edited runner; exact executed bytes are authoritative.
- Executed command: `results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/energy-consistency/run.py --no-plots`.
  Final figure command: the same entrypoint with `--plot-only`.
- `study.json` fixes the flat-road 0–10 s case, nominal/tight LSODA settings,
  four quadrature spacings, and all acceptance limits. The base Baja input,
  reference-model decoder and energy-accounting helper are unchanged.

## Mechanics and evidence locators

The manuscript's shaft-boundary definition includes external applied torques
and referred inertias (`fig:cvt_system_boundary` and the adjoining interface definition). In the installed
release, `execution/hybrid/cvt_impact.py:kinetic_energy_for_topology` uses the
physical velocity map and includes both boundary inertias. The study's
`infrastructure/energy_accounting.py:stored_energy` adds conservative spring
potentials. Its `kinetic_slip_dissipation_power` uses the release's solved
kinetic traction and representative relative contact speed; declared sticking
is not a physical loss channel. `stick_pair_power` is a separate signed drift
diagnostic. The manuscript's `eq:representative_contact_angular_speed` and
`eq:finite_event_energy_loss` supply the relevant power and capture derivations.

`run.py:continuous_segment_balance` integrates power within each segment;
`event_balance` compares exact stored-energy drops with recorded capture losses.
`cumulative_energy_trace` now uses native endpoints, retains duplicate event
times with distinct segment identities, and adds each capture loss after the
incoming segment. The original exporter discarded incoming rows and assigned
event loss by timestamp; that was corrected before the canonical execution.
No simulator mechanics were modified.

Publication checks reconstruct each row's identity, trace/transition state and
energy matches on all native sides, the continuous-plus-event residual, each
quadrature total and the two-finest-grid extrapolate, and the final-state
normalization. All canonical guards pass. Projection energy, momentum,
constraint and nonnegative-loss checks also pass for the tight run, beyond the
original nominal-only event guards. Equal transition counts are checked; this
unit does not claim the separate full hybrid-signature convergence test of 4.2.3.

## Reproduced values and reconciliation

| Quantity | Reproduced nominal | Reproduced tighter ODE | Locator |
|---|---:|---:|---|
| Net work [J] | 52168.893233796545 | 52168.857678203436 | final trace rows; summary |
| Stored-energy increase [J] | 50580.27405641529 | 50580.28742025286 | final trace rows |
| Kinetic-slip loss [J] | 1588.3398738025076 | 1588.3392146392086 | final trace rows |
| Capture loss [J] | 0.2538590432136516 | 0.25388407794207524 | sum of native capture losses |
| Signed final residual [J] | +0.02544453553218773 | −0.02284076657656442 | final trace rows |
| Maximum sampled absolute residual [J] | 0.039778802834007365 | 0.038512683813905824 | complete trace, no mask |
| Native transitions / projections | 16 / 13 | 16 / 13 | both transition/capture ledgers |
| Maximum event-energy defect [J] | 2.2737367544323206e-13 | 2.2737367544323206e-13 | both capture ledgers |

Each trace contains 16,145 rows, including both sides of all 16 transitions.
The nominal work fraction is 4.877338573804363e-7. The final-state comparison is
1.2972799733193834e-7 with the componentwise floors defined in D.2.

The nominal continuous defects at maximum spacings 5, 2.5, 1.25 and 0.625 ms are
0.09074370027736547, 0.040638078219537355, 0.028244179212585478 and
0.025444535658757032 J. The two finest grids give +0.024511321140814214 J by the
second-order Richardson formula. This is the zero-spacing extrapolate of a
fixed numerical trajectory's defect, not an error bar, an assumed exact limit,
or the remaining quadrature error at 0.625 ms. Every short segment has at least
12 intervals, so actual local spacings need not equal the requested maxima.

The historical draft's +0.024510 J extrapolate and −0.022843 J tight residual
are replaced by the reproduced +0.024511 J and −0.022841 J. Differences are about
1–2 microjoules at the displayed precision. Their source cannot be isolated
without the historical raw execution/environment; the current exact inputs and
outputs supersede rounded recap numbers. No claim of byte-for-byte agreement
with unavailable historical raw data is made.

The nominal signed sticking-drift work is +0.0010158023171125787 J. It is not
subtracted to improve the residual and is not called static-friction loss.

## Panel purposes and transformations

(a) Separate signed primary boundary work, signed secondary boundary work and
kinetic-energy increase in kJ, using the complete nominal trajectory. Negative
secondary work removes energy through the resisting load. Attached boundary
inertias remain in kinetic energy. Smaller spring and loss terms stay in the
complete final ledger; the figure does not pretend to resolve them at this scale.

(b) Complete signed residuals, in J, from the nominal and tight trajectories at
the same finest audit spacing. No absolute-value transform, normalized axis,
negative-value clipping, downsampling, smoothing, or regime exclusion.

(c) The interval −20 to +40 ms around each trajectory's own upper-stop capture.
Native times are 6.781920912090633 and 6.781924983147974 s. Relative-time alignment
is only for this display, not a convergence metric. The incoming/outgoing
residuals coincide exactly at each capture. Nominal capture loss there is
1.603747659828514e-5 J, with zero energy defect; the nearby visible residual
change is in continuous integration. The detail prevents the full-time plot
from implying an unaccounted instantaneous loss. It does not identify a unique
source of the continuous defect.

(d) Signed sum of continuous-segment defects against actual maximum power-
evaluation interval h, on a descending base-2 axis. Each step right halves h.
Points are connected only as a visual guide, with no fitted error model.
The horizontal line is the second-order zero-spacing estimate from the two
finest intervals. It is not an error bound or an exact limiting remainder.

All plotted lines are per continuous segment. Every event side is retained at
its true time; no line or trapezoid bridges a velocity reset. The final ledger
compares both ODE settings, with residuals computed before rounding. Stored
energy is separate from modeled irreversible losses. Capture loss belongs in the balance because the inelastic constraint removes
kinetic energy, independently of its magnitude relative to the remainder.

## Scope and integration

Two ODE settings show sensitivity, not an established convergence order or a
unique attribution of the remaining defect. The residual fraction is an
accounting diagnostic, not efficiency or evidence that omitted losses are
negligible. Chapters 1–3, 4.5, Chapter 5, abstract and live simulator source are
unchanged. The necessary methods dependency is D.2: inventory, segment/event
quadrature, Richardson definition and the inactive 1 J denominator floor now
match the runner. Existing main and appendix labels are retained.

Whole-manuscript integration remains incomplete: the global Results archive
metadata, four unresolved cross-references, stale shared Baja metadata hash,
missing declared appendix bibliography, and known 4.5 conflicts are tracked in
the continuation/inventory. None is concealed by this unit's publication assets.
