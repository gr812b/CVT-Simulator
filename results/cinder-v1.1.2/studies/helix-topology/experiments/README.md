# Helix topology exploratory experiments

- `run_reaction_map.py` — E1 frozen quasi-static `M_h=0` boundary map.
- `run_forward_control.py` — E2 ordinary flat full-throttle slotted-reference audit.
- `run_stress_screen.py` — E3 controlled secondary-torque zero-crossing screen from low/mid/high naturally reached states.
- `run_scenario_discovery.py` — E4 broad discovery across hill entry, downhill + engine braking, bench secondary back-drive, bench resisting load, and a high-dynamic natural restart.
- `run_liftoff_envelope.py` — E5 targeted vehicle lift-off thresholds plus full-dynamic-vs-quasi-static novelty refinement.
- `run_dynamic_only_liftoff.py` — E5.5 preload/transient search for forward-power, stick--stick dynamic-only helix lift-off.

Prefer the parent `run.py` rather than invoking these individually. It runs the stages in causal order and produces the handoff ZIP automatically.


The scenario-discovery stage also includes two full-history legacy hill replays
in the normal (non-`--quick`) run.  They are intentionally separate from the
short restart matrix so the naturally evolved pre-hill state is preserved.

### E5.6 `run_transient_severity_race.py`

Maps the race between selected-flank helix inadmissibility and belt traction
saturation under increasingly severe forward-power transients.  It forces the
sub-50 ms engine torque ramps that E5.5 never reached, blends full-throttle
operation to 0/-5/-15/-28 N m primary torque, extends secondary load steps to
-120 N m, and retains sparse opposite-sign controls.  Each preload is fully
reconditioned before 30/50/70% shift restarts are selected.  The primary
classification is `helix_first`, `traction_first`, `simultaneous_or_unresolved`,
or `neither`; the gold condition additionally requires forward power, free
stick-stick contact, positive torque+spring margin, and an interior shift state.


## E5.7 — Coupled event chronology

`run_coupled_event_chronology.py` is a post-processing-only stage. It consumes the completed E5.6 `case_summary.csv` and `retained_trace.csv`, selects a reverse-power helix/traction event and a stock-300° dynamic-term exemplar algorithmically, and writes aligned helix-margin / axial-clamp / normal-force / traction / dynamic-term chronologies. It performs no new CINDER integration.
