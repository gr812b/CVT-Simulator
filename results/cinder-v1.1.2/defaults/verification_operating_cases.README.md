# Shared verification operating cases

`verification_operating_cases.json` is the canonical reusable operating-case
vocabulary for release-level CINDER v1.1.2 verification studies.

Mechanical invariants and closure conditioning consume this same library so a
common state class cannot silently drift between studies. The library is
release-scoped and may contain two kinds of entry:

1. **search recipes**, which describe a reproducible state/load class but only
   become evidence after the consuming study's production classifier and
   admissibility checks accept a candidate; and
2. **targeted reproduction anchors**, used only for rare classes that a broader
   exploratory search already demonstrated to be valid. These anchors are still
   fully reclassified, reintegrated and re-audited every time; they are not
   forced modes or cached answers.

Current ownership split:

- `contact_search`: standard + extended deterministic search domains;
- `contact_branch_requests`: the ten stick/slip/sign requests;
- `targeted_contact_states`: deterministic anchors for `secondary_slip_plus`
  and `both_slip_mp` discovered by the missing-coverage exploration;
- `capability_probe_states`: states that previously terminated only on the
  unilateral helix and should be revisited under the slotted results topology;
- `free_shift_search`: positive/negative `s_dot` search domain;
- `static_rest_case`: zero-speed lower-stop hold recipe;
- `structural_boundary_cases`: directed lower-stop / engagement / low-ratio /
  upper-stop arrivals;
- `stick_cases` and named `free_shift_cases`: compact engaged cases used by
  closure conditioning;
- study-specific guards, convergence grids, maps and report policy remain in
  each study.

The shared library points to `results_reference_model.json`; general v1.1.2
result studies therefore use the bilateral/slotted secondary helix unless an
explicit helix-topology comparison opts out in a fresh process.
