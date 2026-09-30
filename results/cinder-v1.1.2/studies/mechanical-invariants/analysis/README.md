# Analysis

Maintained scientific analysis, synthesis, metrics, and candidate figure/table generation. Presence here does **not** mean an output has been selected for the paper. The root `run.py` remains the canonical maintained-study entry point.

The current 4.2.1 selection is `reader_evidence.py` (physical result values and
case enumeration) and `plot_profile.py` (Appendix D.1 figure). Both are called
by `run.py`. `reconstruct_profile.py` is the frozen, optional selected-case
replay used by a fresh full run. `publication_plots.py` retains the previous
contact-persistence design and shared CSV readers/tests; that figure is no
longer the main-text recommendation.

`sticking_drift.py`, invoked by `run.py --check-stick-drift`, provides the
separate selected-case replay/refinement supporting the velocity-drift
interpretation. It preserves the archived numerical preparation, compares
retained states and event sides, and does not change the full audit. See the
study README for the exact command and scope.
