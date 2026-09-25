# Analysis

Canonical entry point: `run.py --plot-only` from the maintained study, using the
verified release-local CINDER 1.1.2 environment. No simulation is called by this
path. `verification.py` checks registered evidence before publication.

`publication_plots.py` produces four vector PDFs and 300 dpi PNGs:

- `gross_motion_hybrid_history`: main-text full shift and signed early motion, with
  exact low-ratio seating markers for reference, research and selected loose
  calculations. Discontinuous segments are never joined.
- `solver_refinement`: main-text complete formal-grid heatmap: aligned RMS colour
  and separate all-check circles. No interpolated acceptance frontier.
- `solver_acceptance_support`: appendix quantitative RMS, dimensional shift-speed
  peak and event-time trends, plus seven independent absolute-tolerance settings;
  defined metrics only. No fitted convergence order.
- `solver_population_support`: appendix exploratory four-state gross metric,
  exact history grouping and transparent selection of the loose example.

`supporting_plots.py` preserves the formal acceptance display, shared style and
complete-buffer PDF/PNG export. Incomplete PDFs are rejected before replacement.
`reader_values()` recomputes dimensional maxima and native excursion depths and
durations; it verifies the dominant normalized peak and tighter-grid acceptance.
All values and code hashes accompany the figures in JSON.

`evidence.py` registers historical archives, imports them and can replay the one
previously unretained selected history. That replay was done on 23 September;
25 September finalization reuses it. `test_publication_integrity.py` checks exact
history versus count, all guards versus RMS alone, microsecond regime duration,
the four-state exploratory metric, actual jumps versus successor-state flags,
and rejection of modified evidence. See the study README for commands.
