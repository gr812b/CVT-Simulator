# Representative commercial secondary — Yamaha Sidewinder / Dalton YSR

This sub-study anchors the secondary dynamic-coupling generality argument to physically existing OTS hardware.

Primary anchor: **Yamaha Sidewinder YSRC roller secondary + Dalton YSR31 straight helix**. A second local-angle sensitivity uses the published **28 deg terminal segment of YSR36/28**.

The hardware identity, angle catalogue and high-power application context are sourced. Movable-member MOI and effective helix radius are provisional low/nominal/high engineering estimates with explicit equations and provenance.

The result regenerates:
- movable-member mass/MOI estimates;
- `H` and `I_s,M H^2` relative to Baja;
- 31 vs 28 deg local-angle sensitivity;
- prescribed-transient `Pi_s,omega` and `Pi_s,x` surfaces.

Nothing in this directory claims the prescribed kinematics are measured Sidewinder behavior. Better measurements can replace individual input fields without changing the analysis architecture.

Run: `python results/cinder-v1.1.2/studies/actuator-dynamics/commercial-case/run.py`.


## System-level trajectory demonstration

The component sensitivity result is followed by one final experiment:
`run_trajectory_demo.py`.

It replaces only the secondary helix geometry and movable-member rotational
inertia in the otherwise frozen Baja reference machine, then compares the full
dynamic helix with a mechanically matched quasi-static helix under one
preregistered clean load transient.

This is deliberately a **mechanism transplant**, not a Sidewinder simulation.
The unknown Sidewinder spring, primary, track inertia, and other machine
parameters are not invented.

See `TRAJECTORY_DEMONSTRATION.md` and `trajectory_demo.json`.

Run only this result:

```powershell
python .\studies\actuator-dynamics\commercial-case\run_trajectory_demo.py
```

when your current directory is `results/cinder-v1.1.2`.
