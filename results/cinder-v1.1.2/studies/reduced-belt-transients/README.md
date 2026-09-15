# Reduced-belt transient mechanics — broad exploration

## Question

Within CINDER's dynamically closed reduced whole-belt model, **which surviving transient belt terms are active in ordinary operation, what physical situations activate them, and which effects deserve a targeted follow-up before any reduction is attempted?**

This study is discovery-first. It does not contain an ablation switch and does not change the RHS, closure, traction law, actuator mechanics, or hybrid state machine.

## What is measured

Only terms that survive in the **final equations actually solved by CINDER** are treated as scientific channels.

Whole-belt transport:

\[
m_b\dot v_b+\tau_p/r_{p,\mathrm{eff}}+\tau_s/r_{s,\mathrm{eff}}=0.
\]

Independent tension-loop compatibility:

\[
R_{\ddot s}+R_{\dot s^2}+R_{\dot v_b}+R_{\dot s v_b}+R_N=0.
\]

The four transient tension-loop effects are:

- radial shift acceleration, \(R_{\ddot s}\);
- radial geometry curvature, \(R_{\dot s^2}\);
- tangential belt acceleration, \(R_{\dot v_b}\);
- tangential shifting radius, \(R_{\dot s v_b}\).

`R_N` is retained as the contact/load contribution that provides the physical scale of the balance. See `FORMULATION_LINKAGE.md` for the exact expressions.

## Broad exploration protocol

`python run.py` runs four unchanged-model cases derived from the canonical reference simulation document:

1. **ordinary flat launch** — baseline launch plus natural active upshift;
2. **moderate load step** — an 8° grade step at 5 m, then return to flat at 14 m;
3. **strong load step** — the same geometry with an 18° grade step;
4. **severe load/contact-demand exploration** — a 28° step used only to see what the full model naturally does near the high-demand envelope.

These are intentionally broad orientation cases, not optimized stress cases. If the severe case naturally reaches a contact transition, that event is informative; the study does not force one by changing friction.

For a quick algebra-only check without CINDER installed:

```bash
python run.py --tests-only
```

## Outputs

Each case writes:

- `belt_terms.csv` — signed final-equation terms and their physical drivers at accepted solver states;
- `summary.json` — max/median/95th-percentile magnitudes, integrated activity shares, peak context, and final-equation residuals;
- `tension_loop_terms.png` — signed five-term compatibility balance;
- `tension_loop_activity_shares.png` — bounded absolute activity shares;
- `whole_belt_transport_terms.png` — the three final transport terms;
- four driver maps connecting each transient contribution to the state variable that activates it.

The study root also writes `exploration_summary.csv/json` and `cross_case_activity.png` so the same term can be compared across operating conditions.

## Interpretation rule

The broad pass answers **where to look next**, not whether a term may be deleted. The next phase is chosen from the data:

- a term that stays negligible can become a candidate for a coherent reduction derivation;
- a term that appears only during rapid load/shift events gets a targeted timescale study;
- a term whose magnitude changes strongly with shift position gets a ratio/geometry study;
- a term that becomes important near contact transitions gets an event-focused study.

Only after that targeted pass do we define full-vs-reduced models and examine trajectory consequence.
