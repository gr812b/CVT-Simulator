# Actuator dynamics — dynamic coupling and quasi-static validity

This release-scoped CINDER `v1.1.2` study treats the primary fixed-pivot flyweight and secondary torque-reactive helix as one scientific family.

Result sequence:
1. Baja four-model baseline ablation;
2. five component-level dimensionless corrections;
3. coupling-energy/generalized-inertia decomposition;
4. equation-derived validity envelopes;
5. source-registered provisional commercial Sidewinder/YSR scaling case;
6. corrected Baja controlled-transient validation.

`FORMULATION_LINKAGE.md` maps every dimensionless metric directly to the current derivation.

The controlled-target selector no longer allows a distant nearest case to masquerade as a requested target. Current clean-domain targets are primary `0.01%, 0.025%, 0.05%` and secondary `0.5%, 1%, 2%, 2.5%`, with a 25% relative acceptance tolerance.

The commercial case is a physically anchored sensitivity example, not a validated Sidewinder trajectory. Third-party documents are not redistributed; source URLs, supported facts, assumptions and source gaps are stored under `commercial-case/`.

Run:

```powershell
python results/cinder-v1.1.2/studies/actuator-dynamics/verify_study.py
python results/cinder-v1.1.2/studies/actuator-dynamics/run.py
```

Incremental stages may stop at `baseline`, `components`, `coupling`, `envelopes`, `commercial`, or `transients`.


## Commercial-secondary trajectory demonstration

The final actuator result now includes a mechanism-transplant trajectory test.
It uses the frozen Baja machine as the known host and replaces only the
secondary helix geometry and movable-member rotational inertia with the
provisional OTS values. A clean secondary load transient is selected by an
auditable 10–20% dynamic-correction criterion and replayed on full-dynamic and
quasi-static helix models.

This closes the scientific chain from equation-level correction to a complete
system-level trajectory consequence without claiming a fully reconstructed
Sidewinder.

Run only this stage from `results/cinder-v1.1.2`:

```powershell
python .\studies\actuator-dynamics\commercial-case\run_trajectory_demo.py
```
