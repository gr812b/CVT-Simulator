# Unified-course v3 final-check validation

Record generated: 2026-09-20T17:52:11+00:00

## What was executed

* 63 unit/input regression tests passed (40 previous tests plus 23 final-check tests).
* Four complete 732 m sizing runs used the research preset: R00, W85, H28 and B01.
* All ten selected cases were executed using the tight preset on the unified 732 m road.
* Final source CLI smoke test and resume behavior were exercised; smoke intentionally stopped at 3 simulated seconds.
* The final analysis was run on the uploaded 45 m, 18-degree tests and on all ten local final cases.
* The new hill/settling and chronological non-completion figures were rendered and visually inspected. Closely spaced event labels were grouped after that inspection.
* No simulation/core source was changed during the tight campaign; post-processing/report edits were applied afterward.

## Execution environment

The installed wheel is the released CINDER 1.1.2 wheel, SHA-256 `f9c454963006d701b33197bdef3be60abebc591199aef7f4b52f37a7159310c3`.

The local Python/dependency environment differs from the frozen Results stack; these are implementation and case-sizing checks, not replacements for the user’s frozen-environment campaign or independent convergence studies.

```json
{
  "python": "3.13.5 (main, Jul 15 2026, 20:25:40) [GCC 14.2.0]",
  "platform": "Linux-6.18.44-x86_64-with-glibc2.41",
  "machine": "x86_64",
  "processor": "",
  "cpu_count": 5,
  "cinder-cvt": "1.1.2",
  "numpy": "2.3.5",
  "scipy": "1.17.0",
  "matplotlib": "3.10.8",
  "cinder_import_path": "/opt/pyvenv/lib/python3.13/site-packages/cinder/__init__.py",
  "frozen_environment_match": false
}
```

The repository `reference_case.py` and `slotted_helix.py` were read at commit `e65d26599016572c47deb46d46daf18ad2c26c84`; local copies were checked against their Git blob SHA-1 values before execution. The local test initializer only re-exported these helpers. The baseline was the unchanged R00 public document from the uploaded artifacts. None of those shared helper or baseline files is included in the update.

## Course outcomes

| Car | Outcome | Finish time (s) | Maximum distance (m) | Mechanical review |
|---|---|---:|---:|---|
| W115 | finished | 75.689 | 732.000 | False |
| H28 | finished | 75.883 | 732.000 | False |
| R00 | finished | 75.957 | 732.000 | False |
| D02_M | finished | 76.096 | 732.000 | False |
| W85 | finished | 76.169 | 732.000 | False |
| B01 | finished | 76.276 | 732.000 | False |
| D01 | finished | 80.502 | 732.000 | False |
| D02_P | finished | 88.704 | 732.000 | False |
| D02 | progress_limited | — | 192.496 | False |
| U55 | rollback | — | 168.869 | False |

Counts: {'finished': 8, 'progress_limited': 1, 'rollback': 1}. All ten cases had zero inspection errors and zero sampled admissibility review flags.

D02 again reached approximately 192.5 m before rollback and eventual slow-progress censoring. U55 reached approximately 168.9 m before the declared rollback-speed stop. These are observations within this model, not proof of physical impossibility or belt survival under sustained slip.

Both one-change D02 intervention cases finished. Their different whole-course results are hypotheses for mechanical interpretation, not evidence that one hardware setting is universally optimal.

## Interior settling

| Car | Final classification | Last-window mean shift (mm) | Mean vehicle speed (m/s) |
|---|---|---:|---:|
| B01 | observed_steady_interior | 8.31691 | 7.19756 |
| D01 | observed_steady_interior | 11.82903 | 6.42473 |
| D02 | hill_not_reached | — | — |
| D02_M | observed_steady_interior | 9.19653 | 7.19740 |
| D02_P | observed_steady_interior | 4.55065 | 5.84981 |
| H28 | observed_steady_interior | 10.66865 | 7.19050 |
| R00 | observed_steady_interior | 9.54709 | 7.22587 |
| U55 | hill_not_reached | — | — |
| W115 | passing_window_seen_but_not_at_exit | 10.42058 | 7.24695 |
| W85 | observed_steady_interior | 8.54325 | 7.20457 |

Seven of the eight finishers pass the full final-window test. W115 has a near-stationary-looking state history but narrowly fails the deliberately stricter shift-acceleration check (maximum about `0.0005253 m/s²`, versus `0.0005 m/s²`). It is not silently promoted to a passing equilibrium. The other ranges and derivatives pass. Refine that case before making a strict steady-state assertion.

In the coarser research sizing run, several similarly small shift-acceleration excursions exceeded this strict criterion despite flat state plots. The tight rerun was used to check the distinction rather than relaxing the criterion to improve the story.

The previous uploaded 45 m, 18-degree hold lasted only about 3.3 s for the four tested cars. At its exit, shift was still decreasing around 1.3 mm/s and vehicle speed around 1.15–1.17 m/s². The new long hold permits the transient, a sustained interior travelling window, and the exit/recovery to be seen separately.

## Cyclic response

Six 12 m cycles with the 6 m end tapers give four whole full-amplitude cycles. More cycles do not create a sustained large oscillation for every tune: R00/H28 reach or remain at the upper stop earlier; W85/B01 continue free shifting and then progressively encounter the upper stop. The per-cycle data are retained, including the taper cycles. This is a regime/operating-state effect, not a damping identification.

## Delivery and reproducibility

The update contains only new study input, orchestration, post-processing, tests and documentation. It depends on the existing v2 study, installed CINDER 1.1.2, and shared Results defaults. Existing course files, fleet files, mechanics and historical artifacts are not replaced.

Use `--execute --jobs 4 --resume` on `exploration/finalize_course.py`. The wrapper defaults to the tight preset and prints both the normal report and the extra final checks. Criteria and tested windows are written alongside the new report. No automatic course changes, restarts, velocity prescription, or imposed steady-state condition are used.
