# Revision 2

Added optional feature exploration and exact source-only overlay update.

- Original `inputs/course.json` and `inputs/competitors.json` remain byte-for-byte unchanged.
- Optional secondary hill, cyclic mean grade, fixed physical envelope length and flat-only probe.
- Six additional tune probes in a separate fleet file.
- Separate 12-variant/52-case exploration plan; every trajectory starts at the common initial state.
- Per-car phase-coloured primary-vs-secondary speed plots, fleet/family counterparts and offline gallery.
- Feature metrics separate continued upshift from backshift and cyclic modulation.
- All original mechanical assembly and boundary checks retained; no CINDER or shared-default edits.
- Existing simulation artifacts are not shipped, overwritten, retimed, or merged.
- Atomic merges protect feature-plan records when separate groups are launched concurrently.
