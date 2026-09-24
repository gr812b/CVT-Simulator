# Course-feature revision 2: review and test record

## Findings from the uploaded campaign

Source: `artifacts(20260920-154258).zip`, campaign
`course38_w6_h80_v2__screen__58a5425d2888`. Its recorded study-source hashes exactly
match the revision-1 ZIP supplied earlier. The saved environment identifies the
frozen Python 3.12.4 / CINDER 1.1.2 / NumPy 2.5.2 / SciPy 1.18.1 setup.

The campaign contains 32 cars: 31 completed, D02 was censored by the slow-progress
criterion after attaining about 192.50 m. No case carries an inspection/admissibility
review flag in those outputs.

* D02 is already a useful delayed/incomplete-upshift example: its opening-flat
  maximum is **16.3367 mm**, compared with the **19.0500 mm** upper stop. Every
  other entrant reaches the upper stop somewhere on the opening flat. That
  observation alone does not establish what D02 would do on a longer flat.
* R00's whoops-sector shift spans **17.9342–19.0500 mm**, but much of that is
  ordinary upshift. Its largest sampled fall from a preceding shift maximum is
  only **0.0839 mm**. It spends approximately **51.9%** of cyclic-sector time at
  the upper stop, using segmentwise sampled duration accounting.
* W85 has approximately **0.0914 mm** maximum backshift drawdown and stays free
  throughout that sector. Therefore a stop is not the entire explanation for
  weak cyclic response. H28, by contrast, spends approximately **97.5%** of that
  interval on the upper stop, while D01 and D03 remain there throughout.
* B01's approximately **1.94 mm** net shift increase over the cyclic section
  should not be described as a 1.94 mm oscillation: its maximum backshift drawdown
  is only about **0.0922 mm**. This is why revision 2 separates trend, opening
  travel and per-cycle modulation.

These findings motivate separate amplitude, wavelength and mean-load trials,
and a longer flat probe. They do not establish that any one proposed road is
best, or that a particular causal explanation has been isolated.

## New study design

The original 420 m road and original 32-entry fleet are unchanged. The additional
fleet has six under-shift-biased candidates and uses the same mechanism classes,
vehicle parameters, engine map, full-throttle request, friction/contact law and
bilateral helix topology. All affected flyweight moments are changed consistently.

The optional exploration runs 52 full trajectories in 12 campaigns:
8 long-flat runs; 4 secondary-hill roads × 4 cars; 7 cyclic variants × 4 cars.
Every campaign has one common spatial road. A zero-grade added-hill control keeps
the same added length as the moderate hills; a bias-only cyclic control keeps the
same grade envelope as its oscillatory counterpart. No final combined course is
selected or spliced together by this update.

## Local compatibility and execution checks

* **40 unit/input tests pass**, including original tests, feature geometry and
  analytical gradients, shared-approach preservation, fleet invariants, distinct
  partial versus incomplete hill responses, detrending a known synthetic cyclic
  signal, reset-safe plot ordering, and atomic sibling-plan merging.
* A separate simultaneous 10-writer metadata check retained all 10 plan entries.
* The final source passed a two-process, 3 s R00/U55 smoke run and an immediate
  resume run. Both smoke cases correctly report `time_limit`; resume reused both.
* **Six full trajectories were run during development**, listed below. All
  finished with zero mechanical inspection errors and no sampled review flag.
* The old 32-car data were replotted without integration. Every car has a
  road-sector-coloured shift curve; fleet and family views use car colours only.
  Representative old/new plots were rendered and visually inspected.
* Development caught a report import mismatch when files were edited during an
  active run. The completed trajectories were preserved; reports were rebuilt in
  fresh processes. The final-source smoke/report/resume test passes. Concurrent
  feature-plan updates were also changed to locked, fresh-read merges rather
  than allowing one launcher to overwrite a sibling group.

**Environment limitation:** local numerical tests use the released CINDER 1.1.2
wheel, Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0 and Matplotlib 3.10.8. These are
not the user's frozen surrounding library versions. The shared decoder/helix
source was checked against the uploaded campaign hashes (matching after Windows
CRLF/LF normalization). No alternate CVT mechanics were substituted. The full
52-case campaign has **not** been run here, and local figures are preliminary
compatibility/exploration results rather than manuscript evidence.

## Preliminary full-trajectory checks

| Case | Feature | Observation |
|---|---|---|
| R00 | Added 18° hill | Shift falls from 19.05 to **15.1660 mm**, well above the 2.4892 mm low-ratio seat |
| W85 | Added 18° hill | Shift falls to **14.1679 mm** without reaching the low-ratio seat |
| U55 | 800 m flat | No upper-stop arrival; maximum shift **14.90025 mm**. Last 10 s span about 0.00029 mm, still finite-time evidence only |
| R00 | ±32°, 3 m cyclic | Maximum backshift drawdown **0.2576 mm**, approximately 5.36 Hz maximum encounter frequency |
| R00 | ±32°, 12 m cyclic | Maximum backshift drawdown **0.5473 mm**; longer load pulses, approximately 1.34 Hz maximum |
| R00 | ±24° about +8°, 6 m cyclic | Maximum backshift drawdown **0.5493 mm**, no upper-stop occupancy in the cyclic sector |

These tests already expose partial hill backshift and a strong finite-time
under-shift example. The cyclic response is stronger but is not a spectacular
large-amplitude shift oscillation. The complete feature screen should determine
which amplitude/spacing/loading combination remains mechanically interpretable
across multiple tunes. The mean-biased case must be assessed against its bias-only
control before attributing its difference to cyclic excitation alone.

## Metric cautions

Support durations and feature boundaries are reconstructed from saved segmentwise
samples. The exact event records remain authoritative for final timing. The
per-cycle modulation statistic removes a linear spatial trend and fits one
sin/cos pair; it is a descriptive metric, not a transfer-function identification.
The partial-backshift flag is a declared screening criterion, not a model change.
The same unchanged overspeed tails of the full-throttle engine map remain in use.
Rolling grades do not model suspension, tyre lift-off, or jumping over whoops.
