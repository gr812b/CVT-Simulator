# Section 4.2.1 — selected evidence and interpretation

Status: reproduced; selected for author review, not author accepted. The actual
code commit and review status are recorded in the manuscript's
`results-finalization/CONTINUATION.md`.

## Execution identity

- Source: `results-latex` at `5c616eb19775ddb899020153c3869e6972c092ec`.
- Mechanics: installed `cinder-cvt==1.1.2`; tag commit
  `7637a38b4fb9ec21dfb953c1c80a27ec5f389654`. No live `cvtModel/src` import.
- Fresh canonical audit: 23 September 2026, Python 3.12.14, NumPy 2.5.2,
  SciPy 1.18.1, Matplotlib 3.11.1; elapsed 583.04 s.
- Run: `mechanical-invariants-58a8a3a5272cf2c8`. Its retained
  `execution_provenance.json` hashes 17 exact input snapshots and all raw
  JSON/CSV outputs. Inputs were checked byte-for-byte against the baseline
  commit while the unchanged original command ran. The portable identity record
  was added after completion, before plotting; this chronology is recorded.
- Raw outputs were absent from the checkout, so this was a new execution of the
  existing protocol, not a plot reconstructed from the historical recap.
- Base JSON SHA-256:
  `de3e1d27fe7c33d2f72fa9e3d375a44fc9340b51596bc8d29a4b86551e636aaa`.
  Case-library SHA-256:
  `39037f5268abad792c1fd3c60328fe362b39df1526eb49beeace66587b85f0d6`.

The committed `execution_2026-09-23.json` retains the full hash inventory;
`contact_regimes.json` links the selected PDF/PNG and values to the plotting
script hash. The delivery archive also includes the actual raw outputs and
input snapshots for `run.py --plot-only`.

## Claims and their exact sources

| Claim | Evidence / selection | Limit |
| --- | --- | --- |
| 25 classes, 6,257 states, 81 transitions; zero hard failures | `coverage_matrix.csv`, `sample_audit.csv`, `post_transition_audit.csv`; all state and exact-successor guards recomputed before plotting | The classes overlap; these are not 25 independent trajectories or a continuum proof. |
| Largest scaled residual `1.4271624271944376e-14` | `sample_audit.csv`, engaged rows, `closure_max_scaled_residual`; row scaling follows the unchanged core and Appendix D | Historical recap reported `1.11347e-14`. Update the manuscript to the reproduced value; do not claim bitwise identity of all floating-point diagnostics. |
| Three no-exit cases give at least 30 ms | `stick_stick_forward`, `secondary_slip_minus`, `both_slip_pm`; each has a complete 0–30 ms case and no transition record | No extrapolated exit time. |
| Secondary capture at 414.438945 μs, 9.823193 μs and 31.707313 μs | First records for `secondary_slip_plus`, `both_slip_mp`, `both_slip_pp`; reason `contact_restuck_with_static_reserve`; inspected successors | Targeted state construction does not establish operating frequency. |
| Least primary local normal `0.04819889916451533 N/rad`, with simultaneous `N_p=410.85140792481894 N` | `both_slip_mm`, `time_s=0.0017571271742449688`, `sample_location=segment_start` and matching exact successor | This belongs to the continuation after primary slip reversal, not necessarily the initial sign pair. |
| Smallest integrated primary resultant `374.3090219147176 N` is a different state | Same case/time, `sample_location=segment_end`, incoming branch | Never pair independent extrema as though simultaneous on the same event side. |
| Upper-stop coverage comes from the launch | `nominal_baja_reference`, `cvt:upper_stop_reached`, `6.781920912090633 s` | `boundary_upper_stop_arrival` is `MISSING` in `case_definitions.csv`; the dedicated search did not succeed. |

All contact-case dwell times and physical extrema agree with the recap at its
printed precision. The old capability helper used screening-run dwell. The
selected plot and corrected helper use the actual audit's first event instead.
The largest screening/audit difference here is only about 3 ps, but keeping
their identities separate prevents a future misleading comparison.

The code event name `primary_restick` denotes a zero-relative-speed trigger,
not guaranteed sticking. The actual successors include contact exchange and
slip-direction reversal. Appendix D now describes those outcomes explicitly.
The prose reports the observed reversal without inventing an unrecorded static
root or treating numerical reattachment hysteresis as a physical friction law.

## Figure purposes and transformations

| Panel | Reader's question | Variables / subset / transformation |
| --- | --- | --- |
| (a) Contact persistence | Does successful representation imply sustained operation on that initial branch? | Ten canonical cases, same order as Appendix D; first native transition time from t=0; seconds to ms; right-pointing marker for a 30 ms lower bound. Actual accepted `targeted_seed` stage is marked orange. |
| (b) Full-wrap contact | Can a permissible resultant coexist with a very small local contact load? | Separate primary/secondary spatial normal-loading minima, N/rad, then minimum over audited **engaged** states in the 30 ms continuation; includes both event sides and later regimes. The simultaneous resultant for the discussed minimum is provided in the extracted values and prose. |

Both axes are dimensional and logarithmic. Nonpositive values cause a clear
plotting error requiring a new design, rather than being dropped. No smoothing,
trajectory interpolation, event alignment or line across a reset is used. The
analytic wrap field is monotone at a frozen state; its minimum is obtained at
an endpoint rather than estimated on a coarse angular grid. Time is still
sampled, so these are minima among audited states, not a continuous-time proof.

Four initial cases enter the deadzone during their continuation. Their
undefined engaged wrap fields are explicitly excluded, not treated as zero
loads: reverse stick–stick (22 states), primary slip (−) (39), both slip (−,+)
(7), both slip (−,−) (35). No engaged nonfinite value is silently discarded.

The figure exports at 6.5 × 3.25 inches, matching the manuscript's 6.5-inch
text width. PDF and PNG are generated together. `contact_regimes_values.csv`
retains event outcomes, minima, their times/event sides and matched resultants;
`contact_regimes_provenance.json` records the exact script and output hashes.

## Reproduction

The root `run.py` regenerates the audit, the final figure and maintained
postprocessing. `run.py --plot-only` reuses the identified evidence after checking
hashes and state/successor guards. See the study README for full commands and
the clean-output-directory command. The new wrapper does not change the core
mechanics, search order, tolerances, guards or initial-state anchors.
