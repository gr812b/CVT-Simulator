# Secondary retained dynamics — reproducible publication unit

This unit supports Results 4.4.2 and Appendix D.7 in the current manuscript.
The scientific engine is **cinder-cvt 1.1.2**, release commit
`7637a38b4fb9ec21dfb953c1c80a27ec5f389654`. All execution goes through the
release-local environment verifier; the live simulator source is not used.

## Reproduce the final plots, without rerunning a simulation

From the repository root, with the release environment installed:

```bash
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/actuator-dynamics/run.py --plot-only --unit secondary
```

This verifies the compact input hash and exports vector PDF and 300 dpi PNG to
`docs/CVT_Module_Formulation/figures/results/dynamics/`:

- `secondary_continuous_response`: signed force and loaded-minus-own-control motion.
- `secondary_sensitive_transient`: reference rapid-load signed torque terms and small shift difference, followed by primary traction-limit approach and the direct shift-inertia budget.
- `secondary_support`: stock contrast and the **inadmissible formal** reversal continuation, explicitly marked.

`--figure-dir PATH` redirects exports. The existing `--plot-only` command with
no unit argument still reproduces the primary figures.

The 27 September story revision reuses the frozen outputs: **no new simulation**.
It adds the recorded traction values to the compact inputs, uses the exact
incoming reversal rows, and moves the hardware comparison after the reference
cases. The main hardware table reports I, H, I H and I H² with estimate/reference
ratios. The OTS response data are unchanged; its legend was moved off the curve.
The supporting plot is unchanged. Exports are written to temporary files and
completed before replacing the manuscript assets.

The exact plotting dependencies used for this delivery are captured in
`publication_inputs/secondary_plotting_requirements.txt` (Python 3.12). Install
that file instead of the broader release requirements when byte reproduction
of these figures is needed. The figure font is Matplotlib's bundled STIXGeneral.

## Install the exact environment and replay the selected evidence

```bash
python -m venv results/cinder-v1.1.2/.venv
results/cinder-v1.1.2/.venv/bin/python -m pip install -r results/cinder-v1.1.2/requirements.txt
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/verify_environment.py
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/actuator-dynamics/run.py --secondary-publication
```

The last command executes 16 continuations: commercial full/QS × loaded/control
× nominal/tight settings, plus severe and stock full/QS × nominal/tight settings.
It preserves other study outputs, writes `artifacts/secondary-publication-final/`,
then extracts compact inputs and plots. The compact inputs are committed, so
plot reproduction does not require the historical ZIPs. The raw outputs are
provided separately in `CINDER_4_4_2_Frozen_Evidence_2026-09-26.zip`; the main
delivery's `EVIDENCE_ARCHIVE.json` records its identity and hash.

Exact CVT state vectors are in `publication_inputs/secondary_initial_conditions.json`.
The accumulated host angle was not present in the archive and is set to zero;
it is passive for these time-programmed boundaries. It does not affect forces.
The paired cases explicitly retain the supplied sticking mode for both models.
Their initial speed mismatches, traction limits and local loads are audited.
This avoids the short inadmissible sliding reclassification produced by the
small inherited numerical drift in the old common-state protocol.

The original helper now accepts an optional `initial_mode_override`. Its
ordinary behavior is unchanged unless the new publication runner supplies that
argument. The current release-input wrapper no longer stores spring preload in
host constants, so the publication runner sets the actual helix force-law spec.
It does not mutate the frozen reference files or installed simulator.

## Evidence limits that must survive reuse

The commercial nominal and stock comparisons retain positive local wrap loading
at all checked engaged states, including event sides. The severe comparison does
**not** pass that condition after the traction-limit event. Its outgoing primary
minimum is about −0.0760 N/rad (full) and −0.7320 N/rad (QS); these remain negative
under refinement. Plotting code ends each main curve at its incoming event side,
and does not treat a later return to positive loading as repairing the path.
The ≈2.027 mm subsequent shift separation is a formal continuation result,
not an admissible post-slip performance prediction. S1's event/ratio/precision
checks are completed; admissible evidence for that larger post-slip claim is
still absent. Do not silently restore the earlier unqualified claim.

The 7.482 kg helix coefficient is 77.4% of the 9.667 kg **direct shared-shift**
coefficient, not physical CVT mass or inertia after eliminating all coupled
shaft/contact equations. The hardware table instead uses the **local axial**
coefficient I H². The nominal commercial rotational inertia is 5.12 times the
reference, but its smaller H gives 1.49 times the local reflection. Low/high
values are engineering estimates; they are neither measurements nor a pure
inertia sweep.

The legacy commercial generic diagnostics hard-code reference inertia. This unit
uses the dedicated component calculation with the actual assembly inertia and
checks helix force plus spring against the delivered actuator force. Generic
`helix_dynamic_*` columns are not the commercial plotting source. The preserved
archive ratio field is geometric r_s/r_p, not omega_s/omega_p. Event-side forces
are never interpolated through a jump.

## Provenance and historical extraction

`secondary_publication_audit.json` contains exact settings, raw/source hashes,
initial admissibility, native events, local-loading minima, refinement and
archive comparisons. `secondary_archive_audit.json` preserves the prior raw
archive reanalysis, including the low/high hardware range and baseline scale.
`secondary_exploration_audit.json` retains the earlier initialization checks and
the unsuccessful +5 mm compression-preload follow-up. These records have distinct
scopes; earlier entries do not override the final audit.

To recompute the historical archive audit, extract the three recovered archives
under the named directories in the deliverable's `SOURCE_INVENTORY.md`, then run:

```bash
python results/cinder-v1.1.2/studies/actuator-dynamics/analysis/secondary_archive_audit.py --root /path/to/extracted_archive_parents
```

That historical extraction uses NumPy and pandas, and does not import CINDER.
The primary archive inputs are not required for plotting or replaying the final
selected secondary cases. For raw-output re-extraction without integration:

```bash
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/actuator-dynamics/analysis/prepare_secondary_publication.py
```

For the separately extracted evidence, append
`--raw-dir /path/to/evidence/secondary-publication-final`. To write a separate
compact extraction, append `--output-dir PATH`, first copying the committed
`secondary_archive_audit.json` into that directory. The extraction verifies the
commercial force identity, event sides, local contact, and response metrics.

Check the plotted physical quantities without rerunning any dynamics:

```bash
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/actuator-dynamics/analysis/check_secondary_publication.py
```

An optional `--raw-dir /path/to/evidence/secondary-publication-final` also verifies
all 68 raw file hashes. The check retains the expected outgoing failure; it does
not relabel it as admissible. It checks the signed stock torque identity only
where engaged, the incoming primary static limit, positive incoming local loads,
the 77.4% budget denominator, hardware ratios and continuous OTS contact modes.

Exploratory replay flags are documented by
`experiments/run_secondary_publication.py --help`. Omitting `--sticking-start`
reproduces the old mode-reclassification policy; adding `--extra-compression-mm 5
--end-s .45` with a sticking start reproduces the unsuccessful preload follow-up.
Neither policy silently replaces the final publication inputs.

Manuscript integration, previews and the review record live in
`docs/CVT_Module_Formulation/results-finalization/secondary-4-4-2/`.
