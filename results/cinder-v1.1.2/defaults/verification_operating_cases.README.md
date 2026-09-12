# Shared verification operating cases

`verification_operating_cases.json` is the canonical reusable operating-case
vocabulary for release-level CINDER v1.1.2 verification studies.

It was extracted from the current mechanical-invariants operating-domain design
on PR #487 (head `821ac10a...`). Mechanical invariants now **consumes this file
itself**, rather than keeping a second private copy of its case ranges. Closure
conditioning consumes the same library. Solver convergence and later studies can
reuse selected classes where appropriate.

The file stores case/search recipes, not pre-baked solved states. A recipe only
becomes evidence after CINDER's production classifier accepts the requested
topology and the consuming study applies its own physical/admissibility checks.
That lets one shared case mean the same thing across studies without forcing every
study to share the same metric or pass/fail rule.

The main ownership split is:

- `contact_search`: canonical standard + extended fixed-boundary search domains;
- `contact_branch_requests`: stick/slip branch and sign vocabulary;
- `free_shift_search`: positive/negative `s_dot` search domain;
- `static_rest_case`: common zero-speed lower-stop hold recipe;
- `structural_boundary_cases`: directed lower-stop / engagement / low-ratio / upper-stop arrivals;
- `stick_cases` and named `free_shift_cases`: compact engaged cases used heavily by closure conditioning;
- study-specific guards, convergence grids, lambda-map resolution, and report policy remain in each study.

Closure conditioning intentionally ignores deadzone cases because the engaged
2x2 stick-root map does not exist there. Mechanical invariants still uses the
deadzone/static and structural-boundary portions of the library.
