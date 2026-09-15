# Final-equation formulation linkage

This study intentionally begins **after** exact derivation-level cancellations have been performed. A term that is identically absent from the final governing equations is not a scientific magnitude channel here. Such identities belong in derivation/unit verification, not in the results atlas.

## 1. Whole-belt transport

CINDER solves

\[
m_b\dot v_b+\frac{\tau_p}{r_{p,\mathrm{eff}}}+\frac{\tau_s}{r_{s,\mathrm{eff}}}=0.
\]

The exploration therefore records exactly three contributions:

- `transport.belt_inertia_N` = \(m_b\dot v_b\);
- `transport.primary_reaction_N` = \(\tau_p/r_{p,\mathrm{eff}}\);
- `transport.secondary_reaction_N` = \(\tau_s/r_{s,\mathrm{eff}}\).

The pulley radii in this equation are the **effective contact radii** used by the torque balance.

## 2. Closed tension-loop compatibility

For each pulley define the regular contact factors

\[
H_j=\phi_j\left[\Phi_j-(1+E_j)\frac{\Psi_j}{\Phi_j}\right],
\qquad
G_j=\frac{(1+E_j)\sin\beta}{\phi_j\Phi_j},
\]

where \(E_j=e^{-z_j}\), \(\Phi_j=\Phi_-(z_j)\), \(\Psi_j=\Psi_-(z_j)\), and

\[
z_j=\frac{\lambda_j\phi_j}{\sin\beta}.
\]

The CINDER endpoint map gives

\[
T_{j,\mathrm{in}}+T_{j,\mathrm{out}}=2C_j+H_jA_j+G_jN_j,
\]

with

\[
C_j=q\left(v_b^2-r_j\ddot r_j\right),
\qquad
A_j=q\left(r_j\dot v_b+r'_j\dot s\,v_b\right),
\]

and

\[
\ddot r_j=r''_j\dot s^2+r'_j\ddot s.
\]

Applying the independent compatibility

\[
T_{p,\mathrm{in}}+T_{p,\mathrm{out}}-T_{s,\mathrm{in}}-T_{s,\mathrm{out}}=0
\]

removes the common \(2qv_b^2\) term analytically. The actual final balance studied is therefore

\[
R_{\ddot s}+R_{\dot s^2}+R_{\dot v_b}+R_{\dot s v_b}+R_N=0,
\]

where

\[
R_{\ddot s}=-2q(r_pr'_p-r_sr'_s)\ddot s,
\]

\[
R_{\dot s^2}=-2q(r_pr''_p-r_sr''_s)\dot s^2,
\]

\[
R_{\dot v_b}=q(H_pr_p-H_sr_s)\dot v_b,
\]

\[
R_{\dot s v_b}=q(H_pr'_p-H_sr'_s)\dot s\,v_b,
\]

and

\[
R_N=G_pN_p-G_sN_s.
\]

Here \(r_p,r_s\) are the **belt centroid radii**, not the effective torque radii.

## 3. Scientific interpretation

The first four tension-loop contributions are the transient belt mechanics being explored. `loop.normal_contact_N` is retained primarily as the contact/load reference that closes the equation; it is not itself a proposed ablation target.

Each equation receives an instantaneous activity scale equal to the sum of the absolute values of its surviving additive contributions. This gives bounded activity shares without dividing by a residual that should be approximately zero.
