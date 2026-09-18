# Formulation linkage — helix contact topology

This study is deliberately built around the production CINDER helix equations rather than a study-local re-derivation.

## Production dynamic helix

Source: `cvtModel/src/cinder/model/cvt/actuation/forces/helical_torque_reaction.py`.

For the secondary movable member,

```text
tau_h = f*tau_s + k_theta*(theta_pre - theta)
        - I_M*(alpha_s + theta_ddot)
F_h   = tau_h * dtheta/dx_s
```

with

```text
theta_ddot = (dtheta/ds)*s_ddot + (d2theta/ds2)*s_dot^2.
```

The production element exposes `compressive_contact_margin(...) = tau_h`. That reacted torque, not the axial-force sign alone, is therefore the selected-flank unilateral-contact margin used by this study.

The same production element decomposes the axial reaction into:

- torsional spring preload;
- movable-face share of belt torque;
- shaft angular-acceleration term;
- shift-acceleration term;
- helix-profile curvature / shift-speed term.

E1–E5.5 preserve those terms exactly.

## Slotted results reference topology

Source: `results/cinder-v1.1.2/defaults/reference_model/slotted_helix.py`.

`BilateralHelicalTorqueReactionForce` inherits `HelicalTorqueReactionForce` and removes only the unilateral compression-margin hooks. It does not absolute, clip, or delete the signed helix reaction. Consequently:

- `tau_h > 0`: selected slot flank supports the reaction;
- `tau_h < 0`: the opposite slot flank supports the reaction;
- the zero-clearance helix kinematic coupling remains active through the sign change.

That is the E1–E5.5 reference topology.


## E5 quasi-static diagnostic

E5 does **not** introduce a second trajectory model.  Along each full dynamic slotted trajectory it also reports

```text
M_h,QS  = f*tau_s + k_theta*(theta_pre - theta)
M_h,dyn = -I_M*alpha_s
          -I_M*(dtheta/ds)*s_ddot
          -I_M*(d2theta/ds2)*s_dot^2
M_h     = M_h,QS + M_h,dyn.
```

This trajectory-frozen diagnostic answers a precise constitutive question: at the same state and solved belt torque, would deleting the movable-member inertia terms leave the selected flank compressively admissible?  A case with `M_h < 0` and `M_h,QS > 0` therefore isolates a lift-off demand created by the retained dynamic helix terms.  It is not a claim that the complete quasi-static-CVT trajectory would be identical, and it is not a literature-priority claim.

## E5.5 strict dynamic-only diagnostic

E5.5 keeps the E5 trajectory-frozen decomposition but adds operating-state guards.  Its strongest candidate requires

```text
secondary belt internal power > 0
contact regime = stick-stick
M_h,QS > 0
M_h < 0
```

with the crossing in the free interior shift domain and before any post-onset hybrid contact transition.  The preload sweep is fully coupled: a different `theta_pre` is rebuilt into the assembly and the CVT is reconditioned from launch before any restart state is selected.  Therefore a lower preload is not interpreted as a post-processed constant offset.

For the present linear helix the dominant transient term is expected to be

```text
-I_M*(dtheta/ds)*s_ddot,
```

so the study explicitly compares torque drops / resisting-load steps that induce rapid backshift against opposite-sign torque-rise / assist controls.

## Released selected-flank topology

The published/released runtime currently checks mechanism-contact admissibility and terminates if a selected unilateral helix flank would require tensile reaction. The runtime message explicitly notes that lift-off/opposite-flank topology is not modeled.

For the later E6 comparator, a physically consistent detached mode cannot be produced by replacing `F_h` with `max(0,F_h)` while leaving `theta=theta(s)`. Once the selected flank releases, the movable member's relative rotation is no longer constrained by axial shift. The detached formulation therefore needs an independent relative-rotation coordinate and its angular-momentum balance before any re-contact rule is added.

That derivation is intentionally outside the discovery/refinement slice. E1–E4 discover the relevant states; E5 maps their lift-off thresholds and separates the torque+spring quasi-static margin from the retained movable-member inertia terms; E5.5 then tests whether those dynamics alone can flip the flank under forward-power, stick--stick operation before E6 is attempted.

## Sign conventions retained by this study

- Pulley-actuation `closing_force` is positive in the local pulley-closing direction.
- `tau_s` in the closure is belt-on-secondary torque.
- In ordinary forward power transfer, the production secondary rotation equation documents `lambda_s < 0` and `tau_s > 0`.
- The contact-topology sign is always the sign of `tau_h = helix_reacted_torque_margin_Nm`.

Every plotted or integrated opposite-flank metric is keyed to `tau_h < 0` rather than to an assumed axial-force sign.

## E5.6 event-order question

The E5.6 transient-severity study does not redefine the helix mechanics.  It
uses the same reacted-torque margin

\[
M_h=M_{h,\mathrm{QS}}+M_{h,\mathrm{dyn}},\qquad
M_{h,\mathrm{QS}}=f\tau_s+k_\theta(\theta_{\rm pre}-\theta),
\]

and asks which admissibility boundary is encountered first as a forward-power
transient is made faster or larger.  The two event clocks are:

1. the first positive-to-negative crossing of the full \(M_h\); and
2. the first departure of belt contact from stick--stick.

A clean dynamic-only result therefore requires the helix clock to lead the
traction clock while \(M_{h,\mathrm{QS}}>0\), secondary belt power remains
positive, and the shift coordinate is free and interior.  If the traction clock
always leads, the study records that ordering directly instead of inferring a
missing helix topology from a post-slip trajectory.
