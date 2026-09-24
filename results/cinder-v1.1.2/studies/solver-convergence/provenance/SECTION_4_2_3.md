# Section 4.2.3 — evidence and figure provenance

23 September 2026. Unit baseline: `9c3eb35516f7a26e204f4f70f81e5c173540b8f5`;
task branch `results-finalize-4-2-3`. The earlier 4.2.1/4.2.2 work is preserved.
Mechanics: installed `cinder-cvt==1.1.2`, tag commit
`7637a38b4fb9ec21dfb953c1c80a27ec5f389654`; the live 1.1.4 source is not imported.

## What was recovered and what was run

The original archives are registered by complete SHA-256 in
`retained_archives.json`; imported member hashes are in
`artifacts/retained_sources.json`. No full convergence sweep was rerun.

| Retained source | Raw locators after import | Use |
| --- | --- | --- |
| `artifacts(3).zip`, formal revision 4 | `artifacts/main_sweep.csv`, `absolute_tolerance_sweep.csv`, `failed_runs.csv`, `summary.json`, `state_normalization_scales.json` | All 40 formal main cells and all seven independent absolute-tolerance rows. |
| `dense-overnight.zip` | `artifacts/retained_dense/dense_sweep.csv`, `grid.json`, `summary.json`, `failed_runs.csv` | 4,945 exploratory combinations; 4,681 complete, 264 fail. |
| Dense archive reference cache | `artifacts/retained_dense/cache/2c128c4eb06b60ec/` | Native tight-reference segments, transition ledger, compact trace and 2,049-phase-point segment traces. |
| Dense archive research cache | `artifacts/retained_dense/cache/31d6f0938ba3b03a/` | Direct recomputation of the formal research-setting metrics. |
| Newly replayed median example | `artifacts/selected_history/`, `selection.json` | The only new simulation: a missing different-signature trajectory at predetermined median settings. |

All three archived trajectory caches have the reference signature. In particular,
the old extreme overlay `9d4fe6e3dc577397` cannot demonstrate a missed transition.
The new example was selected **before** replay: sort the 609 completed
different-signature rows by their four-state gross RMS, breaking ties by relative
tolerance and maximum step, and take the middle row. Its exact controls are
rtol `0.012684971009663653`, atol `1.2684971009663654e-5`, maximum step
`0.025041423884469123` s, and compact reporting step 0.002 s.

The replay used the current frozen-release decoder and installed release in the
verified release-local environment: Python 3.12.14, NumPy 2.5.2, SciPy 1.18.1,
Matplotlib 3.11.1. It completed in about 4.67 s, with 12 transitions and 486 native
solver points. Archived gross RMS is `0.0001224841065643084`; replayed gross RMS
is `0.00012249756858505778`. These are distinct executions, not recovered original
event timestamps. The original complete dependency lock and machine were not
supplied; the cause of the last-digit difference is not uniquely established.

Execution identity: **`solver-convergence-4f39af8ca42a9693`**.
`execution_2026-09-23.json` is the exact execution record also delivered as
`artifacts/execution_provenance.json`: 17 input snapshots and 36 numerical-output
hashes. Exact executed inputs are delivered under `artifacts/execution_inputs/`.
The replay was made through the new import helper before final CLI routing,
audit and plot/layout revisions. Those snapshots are not overwritten with later
postprocessing code. Scientific integration/comparison functions, case and
decoder are unchanged from the unit baseline. The final code is the reproducible
publication implementation, not a claim that its later documentation existed
at replay time.

The historical case hash `9788bb6a379f9ac23c8508ec0521a8ad0c409a65c07a5ca45166d63111a1da77`
is **exactly** the current `defaults/baja/simulation_case.json` bytes with LF
converted to CRLF. The current LF hash is
`de3e1d27fe7c33d2f72fa9e3d375a44fc9340b51596bc8d29a4b86551e636aaa`.
This resolves the byte-hash discrepancy's newline origin; it does not rewrite
the old shared provenance or establish an unavailable historical dependency lock.

## Definitions and checked outcomes

Formal comparison first requires the exact ordered tuple of event names, outgoing
modes and `has_successor_state`. That Boolean says an outgoing state was supplied,
**not** that velocity necessarily jumped. Reference and research caches each have
16 flags but 13 actual velocity jumps, in matching sequence positions. Endpoint
jump classification uses absolute component differences above `1e-12` solely as
a supplementary roundoff screen. All native states remain in the evidence.

Corresponding segments use equal normalized phase, with 2,049 points including
both ends. Reference segment durations weight the trapezoidal five-state RMS;
zero-duration segments have no RMS weight but remain in the sampled maximum.
No aligned comparison interpolates across resets. A separately implemented
vectorized calculation reproduces the research RMS and maximum.
The scales come from the compact 1 ms reference trace, outgoing at shared event
times, not a continuous supremum. Appendix D.3 records the floors and values.
Event-time differences and exact union-of-boundaries regime durations are separate
guards; different signatures leave aligned metrics undefined, not zero.

The main grid has 39 completed runs and 25 all-guard passes. All 20 cells at
rtol <= `1e-4` pass, but that does not define an interpolated boundary or monotonic
law: the five `1e-3` cells pass while intermediate `3e-4` cells fail the maximum
guard. The `1e-2`/100 ms run fails in inadmissible primary flyweight contact.

Research-setting results, directly recomputed from retained caches:

| Metric | Value | Guard |
| --- | ---: | ---: |
| Five-state aligned RMS | 4.274076392096811e-7 | 1e-4 |
| Aligned sampled maximum | 6.962229851714909e-5 | 1e-3 |
| Maximum event-time difference [s] | 7.986147544325473e-6 | 1e-3 |
| Exact regime-mismatch fraction | 8.457299799607271e-6 | 1e-3 |
| Exact signature | 16 matching transitions | Required |

In the independent atol sweep, `1e-5` and `1e-6` have different signatures.
`3e-6` matches the signature but fails the maximum guard; `3e-8` also fails that
guard despite being tighter than the passing research `1e-7`. This is retained
in the figure, not hidden behind small RMS values or event counts.

The exploratory gross RMS combines the raw-time component RMS values for shaft
speeds, belt speed and shift position only; shift speed is excluded. The compact
candidate trace is linearly interpolated onto reference sample times, unweighted
in time. This historical diagnostic can bridge a reset and includes sampling and
timing effects. It is not formal hybrid acceptance or a convergence-order test.
The different-signature group's median is `1.224841065643084e-4` and 90th percentile
`3.4934314367706174e-4`. Figure grouping uses exact signature, not transition count.

The replay and reference differ during engagement/separation, not stick–slip.
After first engagement, primary separation recurs three versus five times.
Low-ratio seating occurs at `0.0648296015111227` versus
`0.06601241941997818` s. The replay retains a zero-duration engaged segment between
its last engagement and seating at the same time. The reference's final two
contact-free excursions are only 11.051 and 2.023 microseconds; their durations
are tabulated rather than artificially enlarged in the absolute-time figure.
The upper-stop times are `6.784672851485` versus `6.781924680475834` s.
Primary separation removes primary belt force and torque from the active balances
(`eq:deadzone_primary_disengaged`); this supplies the physical reason why gross
upshift agreement alone cannot establish agreement of the local mechanism.

Dimensional sampled raw-time maximum differences for the replay are
0.1204465107 rad/s primary speed, 0.07551327984 rad/s secondary speed,
0.2123916552 m/s belt speed and 0.1342193692 mm shift. These are not continuous
supremum error bounds. Appendix D.3 also retains the archived research/reference
cost comparison (1,156/4,451 native points; 7.257/25.665 s hybrid integration),
with the missing historical machine context explicitly qualified.

## Figure-purpose map and reproduction

| Figure/panel | Reader question | Transform / limit |
| --- | --- | --- |
| Refinement (a) | Which sampled settings pass all tests, not merely RMS? | 40 literal cells; colour is aligned RMS; white circles require all guards; F is failure. No contours. |
| Refinement (b) | Does matching history or a tighter atol ensure every state error improves? | Each of four metrics divided by its own guard; undefined metrics omitted and different signatures marked. |
| Gross/history (a) | How common is small gross error with a different history? | All 4,681 completed rows; exact-signature groups; star selects the predetermined median row. Native points are not RHS calls. |
| Gross/history (b) | Does the selected different history materially alter the full shift curve? | Native segmentwise shift in millimetres versus absolute seconds; no reset joins. |
| Gross/history (c) | Which physical arrangement actually differs? | Native absolute-time primary separated/engaged/seated intervals; no rescaling of short intervals. Zero-duration events retained in records, not given false visible width. |

From `results/cinder-v1.1.2`, restore the delivered `evidence/artifacts/` into
`studies/solver-convergence/artifacts/`, then run:

```bash
.venv/bin/python studies/solver-convergence/run.py --plot-only
```

The study README gives the archive-import/replay command and optional separate
formal-integration paths. New integrations are stored separately and cannot
silently replace the reviewed archived population. Final PDF/PNG, values and
provenance JSON are generated together after hash and scientific checks. Plot
reproduction needs no new simulation. The review record reports the actual
byte-comparison and rendering checks, rather than treating self-review as
independent validation. Other per-point native caches were not retained: their
tabulated guards are audited, not claimed to have been independently reintegrated.
