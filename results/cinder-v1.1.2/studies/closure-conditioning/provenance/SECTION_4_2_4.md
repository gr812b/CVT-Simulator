# Section 4.2.4 — evidence and figure provenance

23 September 2026. Task branch `results-finalize-4-2-4`; unit baseline
`b7a8c836edbe07bb2f4b89fba884dfdfe1ce54c3`. The new branch preserves upstream
`a8b9e7c31567ccea4a3714e59d04d0eb27180141` (title page) and `81a9538`
(appendix/M170 correction), plus the three previously finalized units.
Their original task branches and execution identities remain intact.

Mechanics: installed **cinder-cvt 1.1.2**, tag commit
`7637a38b4fb9ec21dfb953c1c80a27ec5f389654`. The live 1.1.4 source is not imported.

## Exact retained sources

Full archive SHA-256 values and durable source identities are in
`retained_archives.json`. The import registers every selected member hash in
`artifacts/reviewed/retained_sources.json` and retains original numeric bytes.

| Archive | Selected members after import | Purpose |
| --- | --- | --- |
| `artifacts(10).zip` | Not imported into the final run; separately inspected for reconciliation | Earlier recap: 15 × 25 = 375 starts; 81/101/121 map resolutions; upper-stop static-map maximum 338405.4991605586. |
| `artifacts(20260912-044618).zip` | `full/summary.json`, `multistart_*`, `expanded_multistart_*`, `actual_root_state_scan.csv`, `root_jacobian_*`, `states/*/*_map.npz` | Full protocol: 15 × 49 = 735 physical starts; four × 81 = 324 expanded starts; 241/321/501 maps. |
| `best-visual-multiroot-story(1).zip` | `two_contact/`, from `02_row_050_sf0p950_sdotm40_rpm3000/manifold/` | Exact selected state/torques/two roots, inverse grid and approximate continuation curve. Unrelated candidates and the 3-D volume are excluded. |
| `one-contact-multiroot-fold-search.zip` | `one_contact/states_scanned.csv`, `all_one_contact_fold_candidates.csv`, `best/*` | Targeted 62-state search and selected scalar example; 15 candidate rows represent one state/branch/varied-torque geometry. |

The full archive embeds shared-case-library schema 3. Current schema 4 and the
bilateral contact-reference wrapper are not silently substituted for its map
masks. The full study protocol keys match the maintained `study.json` exactly.
The old case hash
`9788bb6a379f9ac23c8508ec0521a8ad0c409a65c07a5ca45166d63111a1da77`
is exactly the current LF file after LF→CRLF conversion. Current LF hash:
`de3e1d27fe7c33d2f72fa9e3d375a44fc9340b51596bc8d29a4b86551e636aaa`.
The old metadata is preserved rather than rewritten.

## What was checked and what was run

**No transient, full traction map or multistart sweep was rerun.** All nine
retained maps were checked: 895,489 points, their dimensions/ranks/condition
maxima and percentiles, plus all signed failure bits and static-box masks.
All 644,488 static/expanded points have numerical rank eight. The broad
mid-shift map has 76,746 numerically rank-deficient points and is expressly
excluded from that rank-eight claim.

The 735 static-box starts include 666 accepted and 69 not accepted attempts.
Every accepted root is within the static limits and within 1e-6 of its state's
mechanically classified operating root. Each starting lattice is checked
against its actual endpoints and resolution. The separate expanded census
contains 324 attempts, 163 accepted: 66/27/37/33 across the four mapped states.
All accepted roots coincide with the existing operating-root clusters.
`accepted` means optimizer success plus sticking compatibility; it is not
itself every mechanical-contact test. Failed starts remain visible/in the data.
The archive does not record iteration paths, so none are drawn.

| State | Static-map maximum κ₂(A_s) | At accepted root |
| --- | ---: | ---: |
| low_ratio_seat | 13260.18608920877 | 10404.7070570235 |
| mid_shift | 36956.50789492616 | 9441.125318278111 |
| upper_stop | 1054035.159800384 | 8560.906484771036 |
| free_shift_opening_70 | 8261.22259750279 | 3621.353444035546 |

The upper-stop maximum lies at λp=-0.21666666666666667,
λs=-0.25458333333333333, failure code 15. Negative integrated normal force,
belt tension and local normal loading reject it independently of the
historical actuator-contact guard. Static capacity is not full admissibility.
Maxima are sampled grid values; expanded and physical grids are not nested,
so a coarser spacing in a wider domain need not increase a sampled maximum.

All 150 retained 2×2 central-difference Jacobians are checked directly by SVD
and determinant, not by trusting the stored condition label. The canonical
h=1e-5 derivative of frozen physical residuals lies on the 1e-6…3e-4 plateau;
maximum relative κ spread is 2.00831740945e-6. Solver/Broyden working-state
Jacobians are never used for the publication conditioning metric.

New work is limited to fresh evaluation of the selected two-contact and scalar
roots; central derivatives; local mechanical correction/refinement of the
retained fixed-primary-torque branch; and a 121×161 focused residual map.
`analysis/frozen_audit.py` reconstructs literal archived kinematics and bench
boundaries with the installed release. It uses no legacy exploration imports.

Execution identity: **`closure-conditioning-2cd896930d63882e`**.
`execution_2026-09-23.json` records 34 exact input snapshots and 43 numerical
output hashes. Snapshots are delivered under `reviewed/execution_inputs/`.
All executed inputs match the maintained source at finalization. The record's
source commit identifies the baseline; its input hashes also identify the new,
then-uncommitted publication code. It does not claim the later documentation
or commit existed at execution time.

Fresh environment: Python 3.12.14, NumPy 2.5.2, SciPy 1.18.1, Matplotlib 3.11.1.
The historical archives do not supply a complete original dependency/machine
lock. Reproducing the final plots from retained arrays and rechecking selected
mechanics does not establish bitwise reproduction of the historical full sweep.

## Selected two-contact result and local correction

Exact state: 95% engaged travel; shift speed -0.04 m/s; primary 3000 rpm;
secondary 3286.525552894801 rpm; belt 22.723828604026963 m/s. Attached bench
inertias are 0.03/0.05 kg m². Primary/secondary boundary torques are
**-81.14811270784904 / +189.9644692158431 N m**. These are signed bench loads,
not nominal vehicle loads or a transient prediction.

The traction pairs are (-0.267610465261353, +0.3340981241613598) and
(-0.3003678174934274, +0.5521247953296619). Both pass static capacity, full belt
loading and mounted actuator contact, under both the archived one-sided and
current bilateral-helix guard. All six checked normal/acceleration quantities
are identical between the two contact conventions (maximum difference zero).
Minimum static margin is μs-|λ|=0.09787520467033817, not a normalized reserve.
Fresh residual norms are below 5.5e-11 m/s²; matrix rank is eight at each root.
Their secondary normals differ: 2400.8545495070152 versus 1668.5962419509287 N.
The dimensional signed accelerations, local normals, tension and derivative
diagnostics are in `selected_audit/two_contact_roots.csv` and Appendix D.4.

The retained inverse-grid curve is approximate. Holding primary torque fixed,
the new code solves R_p=R_s=0 for (λp, secondary torque) at fixed λs, checks
against direct CINDER evaluation and retains an **open** 184-point segment.
The corrected fold is at λp=-0.2856750279272083, λs=0.4134494072456925,
secondary torque 197.39018531193705 N m, 7.42571609609395 N m above the slice.
The archived interpolated maximum was 197.43743762699654 N m (prominence
7.472968411153431 N m). Both records remain available; they are not mixed.
The turn is contact admissible and has full-rank fixed-traction mechanics;
its nearly singular J_R is a numerical local-extremum diagnostic, not an exact
rank certificate. Every displayed point passes the direct sticking-residual
check. Only the secondary local-normal test fails on the dotted end segment.
Secondary traction is the continuation coordinate, not time or physical shift.
The same root IDs, colors and exact torque slice appear in both panels.

## Selected mixed result

At the same 95% travel and -40 mm/s opening speed, primary speed is 2500 rpm,
secondary 2736.7374831140196 rpm and belt speed 18.936523836689133 m/s.
With the same bench inertias, boundary torques are -260 and
+59.34019609296814 N m. Fixed primary traction is -μk=-0.55; secondary roots
are 0.43428795683927435 and 0.5458610486479887. Fresh R_s magnitudes are below
1.8e-10 m/s², scalar slopes about +54.6254 and -28.0426 m/s² per unit λs.
The primary residual is **not** constrained to zero: +364.8347143 and
+379.7702430 m/s² give the required incipient-slip direction at zero relative
speed. No permissive exception fallback is used. Both roots additionally pass
the bilateral reference with identical responses. Local secondary normal
minima are 2.601087936735097 and 0.0061630813618318145 N/rad, distinct from
integrated normals of 1688.2984989342287 and 1386.5858 N. This is a targeted
existence result, not an operating probability or a stable trajectory claim.

## Panel purposes and reproduction

- `closure_robustness.pdf`: sampled matrix sensitivity at fixed traction versus
  actual-root sensitivity; all mid-shift starts and acceptance outcomes. This
  separates the linear response from nonlinear convergence.
- `sticking_closure_fold.pdf`: two simultaneous acceleration zeros at one load,
  and the non-monotone required-torque relation that explains those same roots.
  Failed local contact remains visible as a dotted mathematical continuation.

The canonical commands are in the study README. `--plot-only` verifies the
evidence before plotting; a separate output-directory reproduction matched
both PDFs, both PNGs and both JSON files byte-for-byte. Six focused tests
protect the full/quick distinction, retained failed starts, signed map masks,
same-load/different-response interpretation, scalar/onset distinction and
changed-evidence rejection. No new experimental-validation, universal-uniqueness,
optimal-tune, physical branch-stability or unrun-reduction claim is made.
