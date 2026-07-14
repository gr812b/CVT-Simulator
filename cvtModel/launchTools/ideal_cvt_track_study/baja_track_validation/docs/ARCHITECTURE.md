# Architecture

```text
filled obstacle CSV ──> definitions.py ──> physical rows + grouping contract
                                             │
GPS CSV ──> gps_core.py ──> laps ──> centreline s ──> mapped laps/features
    │                                        │
    └──────> telemetry.py ──> optional driver/CVT context
                                             │
                                             ├─> metrics.py ──> event passes/summaries
                                             ├─> signatures.py -> track-relative anchor evidence
                                             ├─> grouping.py ─> grouping audit
                                             ├─> simulation.py -> comparison metrics
                                             └─> exports.py ──> CSV/XLSX/plots/report
```

## Separation of responsibilities

- `gps_core.py`: proven GPS cleaning, gate/lap detection, centreline construction, ordered map matching, feature projection, spatial profile creation, and plots.
- `telemetry.py`: optional timestamp alignment and canonical naming for throttle, brake, RPM, CVT-ratio, and driven-wheel-speed channels.
- `definitions.py`: strict contract for the finalized CSV. It is the only layer allowed to interpret `FILL`, `N/A`, corrected anchors, and final group IDs.
- `metrics.py`: event geometry, ordered per-pass metrics, robust summaries, simulation cases, and whole-track speed-bin occupancy.
- `signatures.py`: uniform local-anchor windows, track-wide slowdown baseline, configurable strong/moderate/weak classification, and shareable outputs.
- `grouping.py`: evidence-based audit of whether adjacent GPS responses are separately identifiable.
- `simulation.py`: event and full-lap prediction templates and error calculations.
- `pipeline.py`: orchestration without CLI concerns.
- `exports.py`: persistent result tables and run report.
- `cli.py`: command-line interface and error codes.
- `workflow.py`: one-command orchestration and reproducibility manifest for the complete run.

## Resolver boundary

This package does not turn observable geometry into reduced simulator coefficients such as `impact_loss_coefficient_kg` or `effective_lift_fraction`. That remains a vehicle–obstacle interaction resolver problem. The package preserves physical subfeatures and provides measured entry/state-response targets so that resolver/model choices can be tested without pretending GPS supplied those hidden parameters.
