# Final course-tuning revision 3 handoff check

Revision 3 performs a single final-selection substitution: `RC28` -> `R26B7`. The 732 m road, numerical settings, all other vehicles, full-throttle boundary, dynamic fixed-pivot flyweights, bilateral dynamic helix, and R00/U55 supporting flat are unchanged.

The replacement is based on the user's frozen Results-environment `rc28_replacement_v1__tight__14b9d13706e4` campaign. RC28 was rejected at construction. R26B7 passed the released fixed-pivot audit (513 requested/traced positions, one mathematical contact candidate maximum, no findings) and completed the same 732 m course in 75.886206448 s with no recorded inspection errors or sampled admissibility-review flags.

This drop-in updates the final fleet, report groups, tests, selection lock and output revision. It intentionally does not claim a new final root campaign was executed by the packaging environment; the user's next `run.py` execution is the manuscript-facing final campaign.
