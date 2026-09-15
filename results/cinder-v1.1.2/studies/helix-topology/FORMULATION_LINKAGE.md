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

E1–E4 preserve those terms exactly.

## Slotted results reference topology

Source: `results/cinder-v1.1.2/defaults/reference_model/slotted_helix.py`.

`BilateralHelicalTorqueReactionForce` inherits `HelicalTorqueReactionForce` and removes only the unilateral compression-margin hooks. It does not absolute, clip, or delete the signed helix reaction. Consequently:

- `tau_h > 0`: selected slot flank supports the reaction;
- `tau_h < 0`: the opposite slot flank supports the reaction;
- the zero-clearance helix kinematic coupling remains active through the sign change.

That is the E1–E4 reference topology.

## Released selected-flank topology

The published/released runtime currently checks mechanism-contact admissibility and terminates if a selected unilateral helix flank would require tensile reaction. The runtime message explicitly notes that lift-off/opposite-flank topology is not modeled.

For the later E6 comparator, a physically consistent detached mode cannot be produced by replacing `F_h` with `max(0,F_h)` while leaving `theta=theta(s)`. Once the selected flank releases, the movable member's relative rotation is no longer constrained by axial shift. The detached formulation therefore needs an independent relative-rotation coordinate and its angular-momentum balance before any re-contact rule is added.

That derivation is intentionally outside the first exploration slice. The E1–E4 code only discovers and validates the states in which E6 is needed.

## Sign conventions retained by this study

- Pulley-actuation `closing_force` is positive in the local pulley-closing direction.
- `tau_s` in the closure is belt-on-secondary torque.
- In ordinary forward power transfer, the production secondary rotation equation documents `lambda_s < 0` and `tau_s > 0`.
- The contact-topology sign is always the sign of `tau_h = helix_reacted_torque_margin_Nm`.

Every plotted or integrated opposite-flank metric is keyed to `tau_h < 0` rather than to an assumed axial-force sign.
