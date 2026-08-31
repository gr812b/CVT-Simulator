# Ballew 2015 benchmark — permanent CINDER 1.0.0 results home

This directory replaces the legacy
`cvtModel/launchTools/literature/ballew_2015` location. It deliberately carries
**the whole study**, not just a new runner:

- the Ballew thesis used by the benchmark;
- raw WebPlotDigitizer exports and project JSONs;
- prepared Figure 41 / Figure 45 comparison traces;
- every reconstruction assumption and bridge into CINDER;
- the exact legacy benchmark implementation for auditability;
- force-replay and closed-loop historical results;
- convergence and numerical-stability results;
- legacy bug/fix diagnostic artifacts;
- the benchmark-driven CINDER-fix provenance;
- a cleaned runner that executes the published `cinder-cvt==1.0.0` distribution
  without adding the live repository source tree to `sys.path`.

The only legacy material intentionally excluded is Python cache/bytecode.

## 1. Materialize the exact legacy study into its new home

After unzipping this drop-in at the repository root, run:

```powershell
python results/cinder-v1.0.0/studies/ballew-2015/migrate_legacy.py
```

This reads the frozen `cinder-v1.0.0` tag at commit
`ee21850034a58df73ffc4238936ffece8102c4f1`, resolves Git-LFS objects, and maps
the old tree as follows:

```text
ballew-2015/
├── benchmark/                         # cleaned canonical benchmark code
├── reference/                         # exact source + digitization
├── provenance/
│   ├── RECONSTRUCTION.md              # current reconstruction contract
│   ├── CINDER_FIXES.md                # fixes exposed by Ballew
│   ├── CURRENT_STUDY_SUMMARY.md       # carried final interpretation
│   ├── legacy-docs/                   # exact old root Markdown files
│   ├── legacy-code/                   # exact old root Python implementation
│   └── migration_manifest.json        # byte/hash provenance for every moved file
├── artifacts/
│   ├── historical-v1.0.0/             # exact old results/** tree
│   └── rerun-v1.0.0/                  # newly generated clean rerun
├── migrate_legacy.py
├── run.py
├── run_convergence.py
└── study.json
```

The migration does **not** need the old directory to remain in the working tree:
it reads the tagged Git objects directly. If a CSV is stored through Git LFS, the
script smudges the pointer and verifies the materialized content against the
pointer SHA-256. The resulting `migration_manifest.json` records source path,
source Git blob, target path, byte count and SHA-256.

Verify at any time with:

```powershell
python results/cinder-v1.0.0/studies/ballew-2015/migrate_legacy.py --verify
```

Once that passes and the clean rerun matches the historical regression, the old
`launchTools/literature/ballew_2015` directory can be retired without creating a
runtime dependency here.

## 2. What the comparison actually is

This is **not experimental validation**. Ballew Figure 41 and Figure 45 are
outputs from Ballew's own 2015 discretized-belt simulation.

Two complementary protocols are retained:

1. **Force replay** — Figure 45 primary clamp force is imposed on CINDER and the
   resulting primary RPM, secondary RPM and speed ratio are compared with Figure
   41.
2. **Closed loop** — Ballew's published `Kff=1.2`, `Kp=5`, `Ki=75` controller is
   reconstructed around unchanged CINDER. Figure 45 is then an output reference,
   not an input.

No CINDER physical parameter or controller gain is fitted to the digitized
curves.

See `provenance/RECONSTRUCTION.md` for every important source-to-CINDER bridge.

## 3. Why the new study is not a fake all-JSON simulation case

CINDER 1.0.0's serialized simulation-case contract supports built-in
boundaries/hosts/actuators. Ballew needs a tabulated primary-force replay and a
PI controller with an integral host state; those are legitimate Python extension
points but are intentionally not serializable as pretend built-ins.

The cleaned study therefore:

- runs only the verified installed `cinder-cvt==1.0.0` wheel;
- never inserts `cvtModel/src` into `sys.path`;
- constructs only the benchmark-specific extension force/host objects locally;
- validates the assembled physical CVT with `cinder.contracts.validate_assembly`;
- runs through `ComposedCVTHybridSystem.run`;
- projects the result through `cinder.contracts.project_simulation_result`;
- writes `resolved_study.json` containing every published/reconstructed input and
  source hash.

That is the honest v1.0.0 public-boundary implementation.

## 4. Historical results carried with the study

A visible compact copy is already in
`artifacts/historical-v1.0.0/headline/`. The migration then fills in the exact
legacy result tree beneath the same historical directory.

| Protocol | Primary RPM RMSE | Secondary RPM RMSE | Ratio RMSE | Primary-force RMSE |
|---|---:|---:|---:|---:|
| Force replay | 1796.1055 rpm (71.88%) | 38.2552 rpm (3.19%) | 1.4513405 (69.61%) | imposed input |
| Closed loop | 109.6651 rpm (4.39%) | 32.9216 rpm (2.74%) | 0.1092994 (5.24%) | 1180.2276 N (46.04%) |

The force-replay result shows that the two plant models do not have the same
clamp-force-to-shift mapping. The much closer closed-loop speed/ratio result shows
that feedback can place the two different plants on similar macroscopic
trajectories while demanding substantially different clamp histories.

`provenance/CURRENT_STUDY_SUMMARY.md` carries the final interpretation,
convergence result, raw-transition-count caveat and numerical-stability result.

## 5. Re-run against the published release

First bootstrap the release-level environment exactly as PR #476 requires, then
activate it. From `results/cinder-v1.0.0/`:

```powershell
python studies/ballew-2015/run.py
```

Optional:

```powershell
python studies/ballew-2015/run.py --protocol force-replay
python studies/ballew-2015/run.py --protocol closed-loop
python studies/ballew-2015/run.py --no-plots
python studies/ballew-2015/run_convergence.py
python studies/ballew-2015/run_stability_sweep.py --preset smoke
# Broad repeat of the numerical operating-envelope study:
python studies/ballew-2015/run_stability_sweep.py --preset quick
```

Fresh outputs go only to:

```text
artifacts/rerun-v1.0.0/
```

They never delete or overwrite the migrated historical evidence.

## 6. Benchmark-driven CINDER corrections

The original Ballew work exposed implementation defects around:

- one-sided engaged geometry derivatives at a zero-width deadzone boundary;
- unilateral stop release after a discrete contact-topology change;
- completeness of admissible contact successors around kinetic zero crossings.

Those corrections are already part of `cinder-v1.0.0`; the results study does
not vendor or alter CINDER mechanics. Exact historical diagnosis is retained by
the migration and a cleaned explanation lives in `provenance/CINDER_FIXES.md`.
