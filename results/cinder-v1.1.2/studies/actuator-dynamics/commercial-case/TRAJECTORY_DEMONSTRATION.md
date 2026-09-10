# OTS-secondary trajectory demonstration

## Purpose

The commercial component sensitivity study establishes that real high-performance secondary hardware can plausibly produce non-negligible values of the exact dynamic helix terms. This final experiment asks a separate question:

> **If those terms become non-negligible, can they produce a tangible difference in the complete CINDER trajectory?**

A complete Sidewinder reconstruction would require many unpublished parameters. Rather than invent them, this experiment uses a **mechanism transplant**.

## Machine definition

The host transmission remains the frozen CINDER `v1.1.2` Baja reference machine:

- primary clutch and flyweights;
- belt and pulley geometry;
- compression/torsional spring laws;
- engine;
- gearbox/final drive;
- vehicle and road load;
- contact coefficients.

Only two secondary quantities are transplanted from the provisional commercial hardware estimate:

1. the straight 31 deg YSR helix geometry;
2. the secondary movable-member rotational inertia.

This deliberately isolates the dynamic secondary mechanism identified by the derivation.

The commercial secondary **axial mass is not substituted** because it is not part of the present sourced mass-property model and because changing ordinary translational mass would obscure the helix-rotation question.

## Dynamic and quasi-static models

The full model retains the transplanted movable inertia as the helix-constrained rotating member.

The QS comparator uses the same helix geometry and the same total absolute secondary rotating inertia, but removes the relative helix dynamic law. The movable-member MOI is returned to the rigid secondary-shaft inertia. Thus the difference is not created by deleting hardware mass.

## Initial condition

Each model is run naturally to approximately 50% engaged shift and restarted from its own corresponding conditioned state. A zero-disturbance control is also run.

The plotted response is therefore the perturbation relative to each model's own control. The paper-facing comparison is

\[
(\mathrm{QS}_{\rm stress}-\mathrm{QS}_{\rm control})
-
(\mathrm{full}_{\rm stress}-\mathrm{full}_{\rm control}),
\]

which prevents the small baseline difference between the independently conditioned models from masquerading as transient response error.

## Disturbance selection

A finite family of additional **resisting secondary torques** is applied with smooth ramps. The nominal commercial hardware estimate is screened first.

The result is not chosen by maximum trajectory difference. Instead the preregistered rule is:

1. require a clean continuous trajectory;
2. require the quasi-static helix-torque magnitude to stay above 25% of its onset value, so a near-zero normalization cannot manufacture a large \(\Pi\);
3. prefer a naturally generated peak
   \[
   0.10\le\Pi_{s,\rm total}\le0.20;
   \]
4. among qualifying cases, choose the **slowest ramp**, then the smallest absolute torque step;
5. if the band is not reached, report that fact and use the highest eligible clean case only as an explicitly labelled fallback.

The same selected disturbance is then replayed unchanged on the low, nominal, and high commercial mass-property estimates.

## Outputs

The experiment generates:

- `screen.csv` — complete selection screen;
- `selected_case.json` — auditable selection decision;
- `validation_summary.csv` — low/nominal/high system-level consequence;
- raw trajectory samples for all stress/control/full/QS runs;
- full-model component-\(\Pi\) trace;
- shift-response comparison;
- primary- and secondary-speed response comparisons;
- dynamic-component history;
- dynamic vs quasi-static helix-force history;
- uncertainty plots versus the low/nominal/high hardware estimates.

## Claim boundary

A successful result supports:

> *The retained dynamic secondary terms are not intrinsically negligible: when a physically plausible commercial-secondary inertia/helix scale is inserted into the otherwise frozen transmission, a hard but continuous load transient can produce a measurable difference between the full and quasi-static CVT trajectories.*

It does **not** support:

> *This is the transient response of a Yamaha Sidewinder.*

That stronger statement remains reserved for a future fully sourced machine reconstruction.
