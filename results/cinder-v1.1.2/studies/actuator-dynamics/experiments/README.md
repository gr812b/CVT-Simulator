# Actuator-dynamics experiment entry points

These wrappers all materialize and verify the exact `cinder-v1.1.2` tagged
study utilities before execution.

Canonical:
- `run_baseline_ablation.py`
- `run_coupling_energy.py`

Exploratory:
- `run_stress_search.py` (quick by default; add `--full` for the original grid)
- `run_helix_scaling.py` (quick by default; add `--full` for the original grid)

The exploratory scripts are retained to discover useful regimes. Their present
grid axes/thresholds are intentionally **not** treated as final-result design.
