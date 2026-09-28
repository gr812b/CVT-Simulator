# Secondary dynamics: evidence reset, 27 September 2026

## Follow-up — continuous mid-shift evidence recovered, 27 September 2026

The author's recollection was correct. The preceding reset over-weighted the
selected E5.8 stock case and its late re-engagement peak. It did not inventory
the earlier E3 stress traces. Its proposed emphasis on brief engagement events
is superseded as a complete account of the available transient evidence.

The recovered `helix_topology_discovery_artifacts(3).zip` contains the earlier
E3–E5.5 results. E3 starts from the same conditioned state near half travel and
adds resisting secondary-shaft torque over 10 ms, beginning at 0.05 s. Its first
segment remains free and stick–stick. Maximum force corrections in that segment:

| Added resisting torque | Correction | Fraction of simultaneous QS helix force | Travel at peak |
| --- | --- | --- | --- |
| −120 N m | +32.6302 N | 1.49717% | 50.2270% |
| −240 N m | +75.4795 N | 3.49403% | 48.5750% |
| −480 N m | +160.6752 N | 7.56878% | 45.2120% |

All three peaks are at 0.071 s, with negative shift speed (backshift), before
any contact/support transition. In the −480 N m case, shift speed is −0.0756541
m/s; QS/full helix forces are 2122.8682/2283.5434 N. The first transition is at
0.1578200 s, when the low-ratio boundary is reached. Every saved point from
0.060 s to that incoming boundary state has correction above 113.8 N. Thus the
force effect persists through roughly 0.1 s of continuous backshift, rather
than being a re-engagement spike. The shaft-deceleration contribution dominates
at the peak: +2.60740 N m versus −0.02549 N m from shift acceleration and
+0.01757 N m from geometric curvature. These are signed torque contributions;
the axial derivative converts their sum to the reported force.

The corresponding 90%-travel restart reaches +166.9448 N (9.26009%) while
backshifting through 87.0944% travel. The full helix reaction stays positive,
and algebraically reconstructed local wrap minima are positive at every saved
engaged state in all four selected traces. The −480 N m input is a deliberately
severe imposed-load test, not an ordinary reference-vehicle load. These are
full-trajectory force diagnostics; independent full/QS trajectory differences
for these selected E3 cases have not been established here.

The broader E5.6 trace also contains +142.9228 N (10.1772%) during continuous
stick–stick motion in E56_p180_s70_engine-target-torque_m028p00_r001000us.
This uses 180-degree preload and ramps the primary applied torque to −28 N m
in 1 ms. At its force peak the sheaves are still upshifting, so do not label
that peak a backshift. The earlier −1.121 N m pre-traction summary was the
most negative correction, not the largest absolute correction; it missed
this positive 2.31227 N m result if used as a universal magnitude bound.

The approximately 49% interior peak mentioned during the follow-up inspection
needs a separate qualification: it is a roughly 68 ns intermediate contact
segment in the 180-degree/50%-travel reversal, after a brief negative helix
reaction and before local primary loading becomes negative. It is not a clean
continuous example and should not replace the E3 backshift comparison.

Revised selection rule: inventory both signs, duration, physical motion and
contact sequence across the relevant study families before choosing a
representative transient. Re-engagement and sticking are different questions;
large corrections during free backshift must not disappear because a later
extremum is larger. The representative continuous transient must be reconsidered
before redrafting. The useful launch and estimated OTS evidence remains valid.

Reproduction (postprocessing, no simulator import or new integration):

```bash
python3 results/cinder-v1.1.2/studies/actuator-dynamics/analysis/audit_helix_midshift.py \
  --archive /absolute/path/helix_topology_discovery_artifacts\(3\).zip \
  --output results/cinder-v1.1.2/studies/actuator-dynamics/publication_inputs/secondary_midshift_audit.json
```

Archive identity: libfile_b2d9b43f0ff48191b9ff07a523aaec1e; SHA256
`e8878e17baf209d70d821c4254a6b043aefdbe2b077f32cea51613d303ad1f9a`.
Raw source: `artifacts/stress-screen/screen_trace.csv` and `screen_summary.csv`,
case IDs s50_m120_r10ms, s50_m240_r10ms, s50_m480_r10ms, s90_m480_r10ms.
The upstream manifest records frozen release commit
`7637a38b4fb9ec21dfb953c1c80a27ec5f389654`. No targeted refinement was run for
these newly recovered candidates. The new check covers saved force values,
mode/event placement and reconstructed local loading; publication selection
and any needed numerical refinement remain open.

Status: evidence audit and corrected drafting direction after author rejection.
This is not a replacement manuscript, a final figure selection, or author acceptance.
The manuscript and existing figure exports have not been changed in this audit.

## What failed

The previous take was organized around an inherited selection of cases. Its
reviews checked the statements and event qualifications within that selection
without first establishing whether it represented the important parts of the
available histories. That left two substantial omissions:

1. The reference-drive statement covered 0.1–10 s and omitted the much larger
   secondary correction immediately after engagement, already present in the
   same launch used for the primary section.
2. The selected stock-load figure showed only the small initial torque correction,
   although its already-refined, locally audited continuation later contains a
   large force correction at re-engagement.

The severe reversal then became a central example because its invalid post-slip
tail had been replaced with a qualified traction-timing comparison. That repaired
an overclaim, but did not establish that the repaired example was the best way
to teach secondary dynamics. Its appended inertia bar and local-contact warning
made the reader reconstruct a new question. The new H and m_h,ref symbols added
another unnecessary burden. These are evidence-selection and causal-order errors,
not defects that another introductory sentence will solve.

## Recovered results

Percentages below compare the dynamic correction with the simultaneous
quasi-static **helix force on the full trajectory**. They are not percentages
of the total secondary closing force or differences between independently
integrated full and reduced trajectories.

| Condition | Force evidence | Scope and useful inference |
| --- | --- | --- |
| Reference launch, exact outgoing engagement, tighter integration | At 0.0619713467 s: QS helix force 2206.0909 N; shaft contribution −6.6704 N; shift-acceleration contribution −990.6513 N; geometric-curvature contribution +1.6647 N. Net −995.6569 N, or −45.13218%; full helix force remains +1210.4340 N. | The drive already contains a substantial secondary inertial correction at engagement. It is the finite force in the outgoing engaged dynamics, not the engagement impulse. |
| Reference launch, later 0.1–10 s | Maximum absolute force correction 25.42479 N; maximum absolute simultaneous percentage 0.7506448%. | The earlier small-correction claim is correct only for this stated interval. It cannot characterize engagement. The maxima of force and percentage need not occur at the same time. |
| Stock secondary, added resistance at the secondary shaft | Case E58_stock_300_s30_output_m120_r002 adds −120 N m over 2 ms. At 0.3610547698 s (331.05477 ms after onset), re-engagement produces −36.630279 N m, equivalent to −2264.1364 N or −23.046714% of the simultaneous QS helix force. | The large correction is later in the backshift, not in the initial ramp. Full helix torque remains +122.308990 N m there. No helix-reaction sign reversal is required for a large force correction. |
| Same stock case, integrated motion | Existing tighter full/QS audit gives maximum shift separation 0.0514230 mm over roughly 5.2 mm backshift. | A large, brief force correction does not imply a similarly large accumulated shift difference. The first large re-engagement interval lasts about 20.5 microseconds; tiny subsequent seating/re-engagement segments are not evidence for a newly discovered physical oscillation. |
| Larger estimated OTS component, previously audited continuous case | Existing refined result: maximum absolute correction 89.3043 N; maximum fraction 7.87005%; maximum loaded-minus-own-control response differences 0.274148 mm and 40.3648 rpm. | This is the distinct continuous-motion hardware example. All four continuations stick and shift freely. These values were checked in the prior audit, not regenerated here. The mass properties remain engineering estimates; this is not a complete commercial-vehicle reconstruction. |

The corrected stock signed torque terms at the large peak are −0.7122483 N m
(shaft), −35.9180587 N m (shift acceleration), and +0.00002778 N m
(curvature). They have different signs and relative importance from the small
initial response. The author's endorsed initial example remains useful:
approximately +0.444 and −0.891 N m, net −0.448 N m beside 40.43 N m QS.
It explains cancellation at that instant; it does not summarize the whole run.

The helix's majority share of direct shift inertia also need not depend on the
severe reversal. At launch engagement it contributes 4.88604 kg of 6.83180 kg:
71.5191%. Over the sampled engaged launch geometry its share is 71.52–81.73%.
These are direct coefficients in the shared shift coordinate, not physical
sheave mass, reduced scalar inertia after eliminating other equations, or an
error multiplier. A constrained sheave does not accelerate merely because this
coefficient exists.

## Admissibility and refinement

The launch result is present in both the nominal and tighter primary-production
outputs, not only the old baseline archive. The exact outgoing engagement
correction is −995.655627/−995.656912 N, or −45.132357/−45.132180%.
The corresponding times are 0.061965310/0.061971347 s. The earlier part's
maximum absolute correction is −1003.628147/−1003.632395 N. These are different
states from the first-engagement percentage quoted above.

Baseline local wrap loading was newly reconstructed algebraically from the saved
normal resultants, accelerations, signed tractions and one-sided geometry, using
the frozen 1.1.2 endpoint-tension equations. Both endpoints of each wrap determine
the minimum because the retained wrap solution is monotone. No trajectory was
rerun and no closure was re-solved. All stored engaged minima remain positive;
the tighter minimum is 0.850745 N/rad primary and 2.639381 N/rad secondary.
At outgoing engagement they are 7.048613 and 190.186684 N/rad. Deadzone diagnostics
are absent, not zero, and are excluded. This is a sampled postprocessing check,
not a new continuous-domain or experimental validation claim.

The stock correction also survives the existing nominal/tighter refinement:
−2264.136416/−2264.136443 N. At the tighter peak, saved local minima are
+23.812938/+441.610340 N/rad primary/secondary. Across all its checked engaged
states their minima are +9.561474/+20.548074 N/rad; full helix torque stays
above +39.597589 N m. These are retained prior native-state local-contact checks.

The severe reversal E58_reversal_270_s30_engine_m28_r050 is a different case.
Its incoming traction-arrival comparison remains usable, but its outgoing
primary local load is negative (−0.076028/−0.732012 N/rad full/QS).
The excluded approximately 2.027 mm later separation remains inadmissible as
performance evidence. Keep the failed continuation and timing comparison in
support; do not use it to stand in for the admissible large force corrections.
Helix-reaction sign, belt sticking/sliding, and local compressive wrap contact
are different conditions. The previous prose blurred their roles in the story.

The wider historical severity-screen summary was also recovered: its strict
pre-exit stick–stick window has a minimum net correction of −1.12141 N m.
The approximately −36.63 N m whole-trace stock correction occurs after the
initial stick–stick segment ends. Historical labels such as “traction-first”
can include seating/deadzone/re-engagement; they are not sufficient to identify
an isolated static-friction saturation. The full 1 GB broad retained trace was
not freshly audited state by state. No claim is made that every old candidate
is physically admissible.

## Corrected story and display priorities

1. Continue the primary's physical explanation. Relative sheave rotation creates
   resistance to shifting; the secondary additionally couples clamping to shaft
   acceleration. Write dtheta_s/dx_s explicitly. Define the QS force and explain
   the shaft and sheave acceleration terms together: their drivers, signs, and
   growth with inertia and motion ratio. Explain the reflected coefficient
   I_s,M (dtheta_s/ds)^2 inline, without naming a new mass variable. Removing the
   correction removes both accelerations; the separate-body inertia reassignment
   remains explicit and brief.
2. Use the already-familiar reference launch to establish when it matters. Show
   the engagement force correction and the much smaller later correction as
   parts of one history. This connects directly to the primary section and gives
   the reader a real contrast. Put the majority inertia scale beside this
   explanation, not in a detached panel attached to another experiment.
3. A sudden increase in resistance at the driven shaft provides the physical
   motivation for the added-torque case. Explain its initial signed cancellation,
   then identify the later re-engagement correction and the small integrated
   shift difference. The point is the distinction between instantaneous force
   and accumulated motion, not that every rapid ramp produces a large error.
   Use the helix-topology evidence as part of this question, not as a second
   research-project narrative.
4. Broaden to the estimated larger hardware after establishing the reference
   behavior. Preserve the inertia/motion-ratio scaling and the continuous
   force/controlled-response example. Do not attribute the difference between
   dissimilar reference and OTS trials solely to inertia: their operating states,
   ramp times and geometry differ. The existing low/high component comparison
   varies radius and inertia together.

For the next figure revision, the reference-drive force history with an
engagement detail has first priority. Plot the dimensional QS and full helix
forces and enough signed decomposition to explain the difference. The stock
display must not crop away the late event or stretch its microsecond response
to look sustained: show event sides as discontinuities, identify the event, and
place the close shift histories/difference on their actual longer time scale.
A compact stock illustration or supporting figure is preferable to keeping the
severe reversal merely to fill panels. Preserve the useful OTS response figure.
The previous sensitive-transient panel set is reopened; placeholder panels are
not binding final designs. No new final figures are claimed in this audit.

Preserve the endorsed conclusion's physical inference. If the severe timing
example moves to support, review its one contact-timing sentence in context;
do not leave an unsupported main-text reference or silently discard the useful
comparison. Do not claim a large admissible post-slip trajectory effect.

## Reproduction and source locators

Maintained postprocessing:

```bash
python3 results/cinder-v1.1.2/studies/actuator-dynamics/analysis/audit_secondary_windows.py \
  --primary-package /absolute/path/CINDER_4_4_1_Finalization_2026-09-25.zip \
  --output results/cinder-v1.1.2/studies/actuator-dynamics/publication_inputs/secondary_window_audit.json
```

This NumPy-only audit imports no simulator. Its source trajectories were
produced through canonical `actuator-dynamics/run.py --primary-publication` and
`--secondary-publication`, using cinder-cvt 1.1.2 / tag commit
`7637a38b4fb9ec21dfb953c1c80a27ec5f389654`. Those simulation commands still require
the verified release environment. Do not rerun them merely for this audit.

- Primary finalization archive, version 1: Library identity
  `libfile_676a5a7446f0819198710a9ae6e8c847`; SHA256
  `692742ece9ddff7b6f8b532ddb42121a8027b6a3689db63ad45da38f11b0e505`.
  Read `source/results/cinder-v1.1.2/studies/actuator-dynamics/artifacts/primary-publication/baseline_{nominal,tight}_full/`.
  Raw trajectory, event and provenance hashes are checked against the archived
  primary publication audit; geometry bytes are checked against run provenance.
- Maintained `publication_inputs/secondary_publication.npz`, SHA256
  `3cd270d476e48848e956b74d9228201daf622df785beaa2754a7ebca3f4695b7`;
  stock `{nominal,tight}_full` prefixes retain exact segment starts/ends,
  signed helix terms and local contact checks. Its hash and release identity are
  verified against `secondary_publication_audit.json`.
- Original helix archive `helix_topology_discovery_artifacts(5).zip`, Library
  identity `libfile_7cea5409ebac8191bd22134957d1a016`; SHA256
  `1a62f43a587b3fbea8e42c3d14d1886d23a206c7662c92ab8da282ab2fa7bfd2`.
  See `artifacts/transient-severity-race/{summary.json,case_summary.csv}` and
  `artifacts/coupled-event-chronology/`; maintained experiment code defines masks.
- The old baseline archive was recovered first, but all launch numbers in this
  note were then checked against the later nominal/tighter primary production.

Review scope: direct raw/compact evidence and source-formula review; no independent
review, new simulation, final rendered-layout review or manuscript acceptance.
The figure register and cumulative brief mark the previous secondary take as
rejected and the next action as evidence-led revision, not progression to 4.4.3.
