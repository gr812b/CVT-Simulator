# Final contour/story revision — 25 September 2026

This revision uses installed cinder-cvt 1.1.2, source tag commit
`7637a38b4fb9ec21dfb953c1c80a27ec5f389654`. The environment check confirms
Python 3.12.14, NumPy 2.5.2, SciPy 1.18.1 and Matplotlib 3.11.1, and excludes
live simulator imports.

## Recovered evidence

`CINDER_Section_4_2_4_Finalization.zip` was recovered from the author's files
(`libfile_5aa29c608c5c8191b14865f5420b9f71`), archive SHA256
`4545387688fd27ca13403187bf9d1afa44fb8240e9b4141fb455ef79d63e51ee`. All 352 listed member hashes
in its CHECKSUMS.sha256 passed. Only closure-study code and evidence were
recovered; its earlier manuscript prose and other units were not substituted
for the accepted later source. `SECTION_4_2_4.md` below retains the historical
execution and archive identities; this note supersedes its panel design.

The recovered `reviewed/` data preserve execution
`closure-conditioning-2cd896930d63882e`: exact source/input snapshots,
43 output hashes, full maps and censuses, selected-root checks, corrected
184-point local curve and focused residual field. The 197.39018531193705 N m
turn is the corrected direct-mechanics value. The old inverse-grid maximum
197.43743762699654 N m remains historical evidence and is not plotted as the
corrected turn.

## New work and the mask issue

No transient, full map or multistart search was rerun. Only the 121×161 focused
selected-state contact grid was evaluated afresh. Its 19,481 residual pairs
match the recovered field exactly. Of these points, 19,005 pass contact checks;
476 fail the secondary local-compression check. Separate primary contact and
secondary topology margins are retained. The bilateral secondary has no
one-sided flank margin; the primary flyweight guard is still applied.

For the retained upper-stop and mid-shift maps, no simulator evaluation is
needed to prove that the masks are unchanged under the bilateral secondary:
all previously rejected points independently fail an unchanged belt-loading
or support check, and all previously accepted points passed both actuator
checks. This argument is verified point by point and is NOT applied to the
opening-70 map, which has actuator-only failures. It does not merely discard
aggregate mechanism bit 8. The final zero contours exclude every cell touching
a rejected point (`corner_mask=False`), preventing a false contour connection
through an invalid sign-change region.

The new `reviewed/contour_audit/` directory contains its execution/input
snapshots, output hashes, signed contact arrays and check summary. Its source
commit records the baseline from which the audit ran; snapshots identify the
then-uncommitted additions. Later plotting/layout edits do not rewrite that
historical execution record. Current plotting-code identity and numerical
parents are recorded separately in each `closure_figure_provenance.json`.

## Panel selection

`closure_robustness.pdf`: upper-stop equilibrated condition field (unmasked
colours; failures hatched; operating pair and sampled maximum) and mid-shift
dimensional mismatch field (both zero contours, solved root, invalid cells
grey). The four-map maxima/root comparison and complete failed-start census
remain in D.4, rather than consuming another main panel.

`sticking_closure_fold.pdf`: same dimensional residual/zero-contour language
for the selected two-root slice; corrected required-secondary-torque curve
at fixed primary torque, with the SAME two roots and load. The curve is open,
ordered in secondary traction, and dotted after loss of local wrap compression.
Different normal loads are shown explicitly. No panel is a time trace.

## Reproduction

From `results/cinder-v1.1.2`, with delivered `evidence/reviewed/` copied to
`studies/closure-conditioning/artifacts/reviewed/`:

```bash
.venv/bin/python verify_environment.py
.venv/bin/python studies/closure-conditioning/verify_study.py
.venv/bin/python studies/closure-conditioning/run.py --plot-only \
  --figure-dir studies/closure-conditioning/artifacts/reviewed/publication
.venv/bin/python studies/closure-conditioning/tests/test_publication.py
```

`--plot-only` verifies both execution records and the signed data before
plotting. It does not recalculate mechanics. To repeat only the new contact
audit, copy the historical reviewed evidence to a NEW destination, excluding
`contour_audit/`, and use:

```bash
.venv/bin/python studies/closure-conditioning/run.py --audit-contours \
  --artifacts-dir /path/new-reviewed-copy
.venv/bin/python studies/closure-conditioning/run.py --plot-only \
  --artifacts-dir /path/new-reviewed-copy --figure-dir /path/new-plots
```

The audit refuses to overwrite an existing `contour_audit/`. The older
`--import-retained FULL_ZIP TWO_CONTACT_ZIP ONE_CONTACT_ZIP` route remains
available for redoing the original selected checks plus the new contact audit
from the exact registered archives. It must also target a new directory.
The historical full sweep's complete original dependency/machine lock is
unavailable; these commands reproduce publication evidence, not a claim of
bitwise historical sweep regeneration.

## Export-integrity correction

The final packaging check detected an incomplete working PDF copy of the first
figure. A completed regeneration matched both its recorded export hash and the
complete asset used in the inspected manuscript preview. Final assets were
replaced and the exporter now writes temporary files, checks PDF completion,
and renames closed files atomically. The final six-file reproduction and PDF
parser/EOF checks pass. No scientific value, contour or manuscript text changed.
