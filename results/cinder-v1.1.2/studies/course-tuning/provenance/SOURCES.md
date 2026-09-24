# Source and selection record

The physical case set was selected from the user's uploaded campaign:
`unified38_c6a32w12_h18hold240__tight__632317402693` in
`artifacts(20260920-183308).zip`.

The selected road, ten tune parameter dictionaries, initial conditions,
checkpoint cadence, stop rules, diagnostic interval and solver controls are
retained. The supporting 800 m flat uses R00 and U55 at the same final tight
controls; its earlier exploratory reference used the research preset.

The study-local mechanical assembly, course evaluator, tune edits, integration
loop, diagnostics and original metric kernels were promoted from the supplied
initial study plus its v2 and v3 updates. The exact unchanged files are listed
in `inherited_implementation.json`. The new work is a fixed-suite runner,
selection checking, result isolation/resume checks and combined reporting.
Plot/report changes do not alter the governing solve or its checkpoints.

The external runtime sources remain:

- Installed `cinder-cvt==1.1.2`, source tag `cinder-v1.1.2`, commit
  `7637a38b4fb9ec21dfb953c1c80a27ec5f389654`.
- Release-scoped `defaults/baja/simulation_case.json` and
  `defaults/reference_model/` from `gr812b/CVT-Simulator`.
- Shared reference helpers reviewed at commit
  `e65d26599016572c47deb46d46daf18ad2c26c84`; their normalized hashes match the
  helpers recorded in the accepted upload. They are not copied into this
  install ZIP. They are snapshotted into each generated results archive.

There are no imports from the exploratory study and no downloads, Git materialization,
CINDER source patches, reduced actuators, fitted outputs or per-car road changes.
Neither D02's non-completion nor any other expected outcome is used as a target
in the runner or acceptance checks.
