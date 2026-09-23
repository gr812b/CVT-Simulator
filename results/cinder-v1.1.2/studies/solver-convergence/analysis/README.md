# Analysis

The root `run.py` is the canonical entry point. Results 4.2.3 selects
`publication_plots.py` for two publication figures; its `publish()` function is
called by `run.py --plot-only` after `verification.py` checks the evidence.

`evidence.py` registers and imports retained archives, deterministically selects
one missing history for replay, and records exact inputs/outputs. No full sweep
is silently rerun. `test_publication_integrity.py` tests the distinctions that
matter to the claim: exact signature versus count, all guards versus RMS alone,
microsecond regime duration, the four-state exploratory metric, actual jumps
versus successor-state flags, and hash failure on modified evidence.

The two final panel sets are `solver_refinement` and
`gross_motion_hybrid_history`. The optional explorer and its old candidate plots
remain distinct from these selections. See the study README and provenance note.
