# Secondary dynamics: launch, continuous backshift, hardware

This revision replaces the rejected early-ramp/reversal-led main selection.
Mechanics remain **cinder-cvt 1.1.2**, tag commit
7637a38b4fb9ec21dfb953c1c80a27ec5f389654. Six full loaded integrations were previously executed in the verified release-local
environment. Ten new runs add the quasi-static loaded cases and both models’
unforced controls at the same nominal/tighter settings. The launch and OTS/stock/
reversal outputs were reused. No live simulator code was imported.

## Evidence and interpretation

1. The full reference launch already contains a −995.6569 N (−45.1322%) helix
   correction at its exact outgoing engagement. The 0.750645% bound is only
   for t >= 0.1 s. The figure separates those intervals instead of concealing
   engagement. There is no independent secondary-QS launch trajectory claim.
2. Three added resisting secondary torques (120/240/480 N m) share one archived
   restart and a 10 ms ramp. Six nominal/tighter continuations to t=0.15 s
   remain in one free stick–stick segment. Refined peaks are
   +32.6270/+75.4894/+160.6436 N. The corresponding same-state percentages
   are 1.49690/3.49514/7.57270%; separately maximizing percentages instead gives
   1.49791/3.50415/7.635995%. The largest full-trace refinement change is
   0.0673863 N. The severe case's correction remains above 113.799 N from
   ramp completion to the common end. The revised right panel compares independently integrated full/QS shift
   responses, subtracting each model’s own no-added-load continuation. At 100 ms
   after load onset, their separations are 0.0497688/0.0962642/0.1761331 mm.
   Under the largest load, the responses are −8.1407448 and −7.9646116 mm.
   The maximum refinement changes of those differences are
   0.0000096711/0.0000075966/0.0000645397 mm.
3. The estimated OTS component extends the independently integrated comparison:
   +89.3043 N peak magnitude, 7.87005% maximum fraction, 0.274148 mm maximum
   shift-response separation and 40.36479 rpm primary-speed separation.
   Each model's own unloaded continuation is subtracted. Inertia and effective
   helix geometry change together; no inertia-only causal attribution is made.
4. The severe reversal's outgoing local failure remains in the appendix.
   Its 2.027 mm formal post-slip separation is excluded from performance claims.
   The valid stock case's large, very brief re-engagement correction and small
   accumulated motion difference also remain in support.

The majority direct shift-inertia share (71.5–81.7% on the sampled launch
geometry) is explained in prose. It is neither a force-error fraction nor a
physical mass. No H or m_h,ref shorthand is introduced in the new main passage.

## Source identities

- Primary finalization ZIP: SHA256
  692742ece9ddff7b6f8b532ddb42121a8027b6a3689db63ad45da38f11b0e505.
  Source: source/results/cinder-v1.1.2/studies/actuator-dynamics/artifacts/primary-publication/baseline_{nominal,tight}_full/.
  The full traces, not primary-QS traces, supply secondary launch diagnostics.
- Earlier helix ZIP(3): SHA256
  e8878e17baf209d70d821c4254a6b043aefdbe2b077f32cea51613d303ad1f9a.
  Member artifacts/stress-screen/screen_trace.csv, case s50_m480_r10ms,
  t=0 segment_start, supplies the common initial coordinates. The remaining
  two selected loads have the same conditioning. The exact vector, mode,
  initial reaction and passive-host-angle policy are in
  publication_inputs/secondary_backshift_initial.json.
- Reused compact OTS/stock/reversal data:
  secondary_publication.npz, SHA256
  3cd270d476e48848e956b74d9228201daf622df785beaa2754a7ebca3f4695b7.
  Its complete original run provenance is in secondary_publication_audit.json.
- New compact launch/backshift data: secondary_story.npz; its authoritative
  hash and all 64 loaded/control raw output hashes are in secondary_story_audit.json.
  Every new run also records the executed source hashes, settings, runtime
  import path, native segment and local-wrap/closure audit.

## Reproduce

From the repository root, create the exact runtime if absent:

~~~bash
python3.12 results/cinder-v1.1.2/bootstrap.py
~~~

Regenerate the four publication figures from the committed compact outputs,
without rerunning dynamics:

~~~bash
results/cinder-v1.1.2/.venv/bin/python \
  results/cinder-v1.1.2/studies/actuator-dynamics/run.py \
  --plot-only --unit secondary
~~~

An alternate destination can be supplied with --figure-dir DIRECTORY.
The maintained generator writes secondary_launch, secondary_backshift,
secondary_continuous_response and secondary_support, each as PDF and PNG.
It preserves native segments and does not interpolate forces over events.

Repeat the sixteen full/reduced loaded/control integrations, reuse the verified
launch archive, compact
and plot:

~~~bash
results/cinder-v1.1.2/.venv/bin/python \
  results/cinder-v1.1.2/studies/actuator-dynamics/run.py \
  --secondary-backshift-publication \
  --primary-archive /absolute/path/CINDER_4_4_1_Finalization_2026-09-25.zip
~~~

The run stops at t=0.15 s by design: this is the common continuous window
selected for the main figure, not a claim that later events cannot occur.
The original E3 histories and their full-window checks remain in
SECONDARY_EVIDENCE_RESET.md and secondary_midshift_audit.json.
The existing --secondary-publication path replays the OTS/stock/reversal
pairs; those already verified runs need not be repeated for plot reproduction.

Verify the quantities and native masks, optionally including the new raw files:

~~~bash
results/cinder-v1.1.2/.venv/bin/python \
  results/cinder-v1.1.2/studies/actuator-dynamics/analysis/check_secondary_publication.py \
  --backshift-dir results/cinder-v1.1.2/studies/actuator-dynamics/artifacts/secondary-backshift
~~~

The compact extractor is analysis/prepare_secondary_story.py. It requires
the verified primary ZIP and the new raw backshift directory; it imports no
CINDER engine. Launch local loading is algebraically reconstructed using
the frozen wrap solution. New backshift local loading and balances are checked
through fresh 1.1.2 closure evaluations. The recorded checks are sampled,
including native endpoint states, not continuous-time admissibility proofs.

The runtime dependencies remain Python 3.12, NumPy 2.5.2, SciPy 1.18.1 and
Matplotlib 3.11.1. Numerical refinement covers the selected cases; no universal
accuracy, root uniqueness, experimental validation or unrun reduction is claimed.

## Backshift reduction and reporting guard

The common initial coordinates are used by the full and reduced secondary,
including the same small inherited sticking-speed mismatch (0.00709 mm/s
maximum). Both independently solved initial closures are admissible. The
full model retains the archived initial reaction guard of 35.72917028 N m;
the quasi-static reaction is solved independently before integration as
35.73692149 N m and checked against the first chronological reporting state.
It would be incorrect to demand the full model’s initial reaction from the
reduced model at those same coordinates. Neither guard is skipped.

Each model’s zero-added-torque continuation removes its existing shift from
its loaded history. The full/QS comparison is between these two responses;
it is not merely a same-state force diagnostic. Before the load, the largest
loaded-minus-control residual is below 4e−7 mm. All sixteen runs retain one
free stick–stick segment, positive tension and positive local wrap loading.
The sampled minimum static margin is 0.543818; maximum sticking-speed
mismatch is 0.015543 mm/s. Fresh reporting and audit closures agree exactly
in the saved coordinates; maximum dimensional balance residual is 1.48e−11.

The helix study helper now accepts an optional reporting_variant, retaining
its full-model default for all previous callers. This passes the correct
reduction identity to the existing sampler. Its candidate full-mechanism
force diagnostics remain counterfactual on QS trajectories by design; the
compact QS data use only motion, mode and local-contact fields. Full force
curves use full-model trajectories exclusively. No frozen CINDER source changed.

The six existing full loaded runs and their source hashes are reused; their
script hashes therefore precede the addition of the reduction/control option.
Each new run records the exact executed code. A preliminary tight QS run was
repeated after correcting its reporting-variant metadata; only the final
correctly labelled outputs enter the package.
