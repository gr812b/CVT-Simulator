# Retained-output review for Results 4.4.3

This is an audit and story checkpoint, not finalization of the belt unit.
No simulation was rerun and no production mechanics changed.
Scientific mechanics remain CINDER 1.1.2, tag commit
`7637a38b4fb9ec21dfb953c1c80a27ec5f389654`; live simulator source is excluded.

Input: `artifacts(20260916-222846).zip`, 60,247,504 bytes, SHA256
`9bacf2c5e8df301aa1e1a8bc080de1798222d749e7d338bf5331447da16a98cb`.
Library identity: `libfile_173b1e03875481919d86bc6a359913ba`.
The complete input contains 1,101 archive members. The audit reads case term
traces, exact input documents, protocols, run summaries and the root comparison
tables directly from the archive; their member hashes are in its JSON output.

From repository root, with the frozen CINDER 1.1.2 environment:

```sh
results/cinder-v1.1.2/.venv/bin/python \
  results/cinder-v1.1.2/studies/reduced-belt-transients/run.py \
  --audit-archive /absolute/path/to/artifacts\(20260916-222846\).zip
```

`--audit-output /absolute/path/to/review.json` permits clean reproduction.
This route exits before simulation, output-tree deletion or test-suite execution.
The default output is `publication_inputs/archive_review.json`. Exact original
Windows input-source strings remain archived provenance, not runtime paths.

The local reconstruction evaluates the frozen regular endpoint map and
`n=(T-C)/sin(beta)`. Its constant radial offset makes tension and normal loading
monotone along a wrap, so the endpoint minimum is exact for each saved state.
Wrap angle is recovered from the saved factors as
`phi=(2*sin(beta)-lambda*H)/G`. Both wrap angles sum to 2*pi. Endpoint-sum
differences are checked against the saved tension-equation residual. This is
postprocessing of retained outputs, without a new closure solve or integration.

R1 repeats the original metric exactly: 1,000 uniform comparison times on the
shared engaged interval; sorted native samples; last duplicate-time value;
linear interpolation; per-state normalization by max(range, max(abs), 1e-12).
Every recomputed normalized value is checked against its archived CSV within
1e-13. Reported percent is 100 times that fraction. Do not use this historical
metric to suppress or smooth a discontinuity in a final manuscript plot.

Two focused tests check fraction/percent conversion and reconstruct a signed
traction wrap whose integrated loading must recover the supplied resultant,
including zero traction. Run from this study directory:

```sh
../../.venv/bin/python -m unittest discover -s tests -p test_archive_review.py -v
```

Both tests passed. The canonical audit was regenerated to a clean output
directory and reproduced byte-for-byte. Its SHA256 is
`c91b37d34b0e3ca275a3c42ef697a88c706a620a3f4f0ce80b54096e0d582ab6`.
The complete manuscript remains byte-unchanged, SHA256
`39243c311c07b98b70f8dfde5fed90663ee1ad5b24c0a425334b931bd3d120d4`.

The existing simulation route clears the study's generated `artifacts/` tree
before running. Keep recovered evidence outside that directory and add a
separate publication-output route before selected refinement/R2 integrations.
The audit route itself never clears that tree.

The current environment passes the release verification: CINDER 1.1.2 from
site-packages, NumPy 2.5.2, SciPy 1.18.1, Matplotlib 3.11.1. The historical
archive is owned by this frozen study, but lacks a complete executed-runtime
manifest. Do not imply a stronger attestation than the available provenance.

Read the manuscript unit's `REVIEW_AND_STORY.md` and `CONTINUATION.md` for the
corrected claims, numerical limitations, remaining R2 experiment, and proposed
figure jobs. Existing discovery recommendations are superseded where they
conflict with this review. A publication build remains pending.
