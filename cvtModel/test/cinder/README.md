# CINDER system-level checks

This directory contains scenario-level physical audits for the real segmented
CVT solver. These are not isolated unit tests and do not replace calibration
or experimental validation. Each scenario integrates the complete operating
regime dispatcher, then checks invariants over accepted trajectory states and
explicit transition resets.

Run the core transition suite from the repository root:

```powershell
python test/cinder/run_hybrid_system_checks.py --no-show
```

Run the longer operating scenarios separately:

```powershell
python test/cinder/run_hybrid_system_checks.py --scenario upper_stop --no-show
python test/cinder/run_hybrid_system_checks.py --scenario one_second --no-show
```

The audit logic lives here rather than under `src/cinder/` because it is test
support only. Production mechanics remain free of test-only dependencies.
