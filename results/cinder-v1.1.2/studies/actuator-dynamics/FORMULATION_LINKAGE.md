# Actuator-dynamics result metrics and formulation linkage

The result metrics below are direct normalizations of terms already present in the current derivation.

## Secondary helix

Define

\[
\tau_{h,\mathrm{QS}}=\frac{\tau_s}{2}+k_{s,\theta}(\theta_{s,\mathrm{pre}}-\theta_s),\qquad
H=\frac{d\theta_s}{dx_s},\qquad H'=\frac{d^2\theta_s}{dx_s^2}.
\]

The current movable-secondary rotational balance contains

\[
-I_{s,M}\left[\dot\omega_s+H\ddot x_s+H'\dot x_s^2\right],
\]

while the corresponding quasi-static helix force is

\[
F_{h,\mathrm{QS}}=\tau_{h,\mathrm{QS}}H.
\]

The three component corrections are therefore

\[
\Pi_{s,\omega}=\frac{I_{s,M}|\dot\omega_s|}{|\tau_{h,\mathrm{QS}}|},\qquad
\Pi_{s,x}=\frac{I_{s,M}|H\ddot x_s|}{|\tau_{h,\mathrm{QS}}|},\qquad
\Pi_{s,c}=\frac{I_{s,M}|H'|\dot x_s^2}{|\tau_{h,\mathrm{QS}}|}.
\]

For a straight constant-angle helix,

\[
H=\frac{1}{r_h\tan\alpha_s},\qquad H'=0,
\]

and the reflected local axial inertia is

\[
M_{h,\mathrm{ref}}=I_{s,M}H^2.
\]

The helix motion-ratio factor cancels only from the **shaft-acceleration component** after normalization by the quasi-static helix force. It remains explicitly in the axial-acceleration and curvature terms, as well as in the reflected inertia.

## Primary flyweight

With

\[
F_{\mathrm{fw,QS}}=\frac12\omega_p^2\frac{dJ_{f,p}}{dx_p},
\]

the two retained dynamic terms give

\[
\Pi_{p,a}=\frac{I_f(dq_f/dx_p)^2|\ddot x_p|}{|F_{\mathrm{fw,QS}}|},\qquad
\Pi_{p,c}=\frac{I_f|(dq_f/dx_p)(d^2q_f/dx_p^2)|\dot x_p^2}{|F_{\mathrm{fw,QS}}|}.
\]

The commercial generality example focuses on the secondary because the real helix angle and physically distinct movable secondary member can be sourced more transparently than a complete commercial primary flyweight mass/constraint map.

## Interpretation

A large component `Pi` means that one dynamic actuator term is materially different from the corresponding quasi-static force scale at that state. It does not by itself guarantee an equally large whole-CVT trajectory difference; that consequence is checked separately through full-vs-quasi-static integrations.
