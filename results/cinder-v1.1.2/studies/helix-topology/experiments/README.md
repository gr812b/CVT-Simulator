# Helix topology exploratory experiments

- `run_reaction_map.py` — E1 frozen quasi-static `M_h=0` boundary map.
- `run_forward_control.py` — E2 ordinary flat full-throttle slotted-reference audit.
- `run_stress_screen.py` — E3 controlled secondary-torque zero-crossing screen from low/mid/high naturally reached states.
- `run_scenario_discovery.py` — E4 broad discovery across hill entry, downhill + engine braking, bench secondary back-drive, bench resisting load, and a high-dynamic natural restart.

Prefer the parent `run.py` rather than invoking these individually. It runs the stages in causal order and produces the handoff ZIP automatically.
