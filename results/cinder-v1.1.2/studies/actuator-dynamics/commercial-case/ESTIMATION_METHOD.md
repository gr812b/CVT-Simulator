# Provisional commercial-secondary estimation method

All inputs are classified as sourced, derived, or engineering-estimated. The selected hardware is real; unpublished mass properties are not presented as facts.

## Movable-member estimate

The sliding member is approximated as a volume-equivalent annular aluminum face plus compact cylindrical hub:

\[
V_f=\pi(R_o^2-R_i^2)t\phi,\quad m_f=\rho V_f,\quad I_f=\tfrac12m_f(R_o^2+R_i^2),\quad I_h=\tfrac12m_hR_h^2.
\]

Then `I_s,M = I_f + I_h`. Low/nominal/high assumptions are stored explicitly in `inputs/sidewinder_ysr31_provisional.json`.

## Helix geometry

For a straight local helix,

\[
H=1/(r_h\tan\alpha).
\]

The sourced straight YSR31 is the primary case. The sourced 28 deg terminal segment of YSR36/28 is evaluated only as a local constant-angle sensitivity because the transition profile/location is not published.

## Reflected axial inertia

\[
M_{h,\mathrm{ref}}=I_{s,M}H^2.
\]

## Prescribed-transient sensitivity

No measured Sidewinder sheave-position transient was found. A rest-to-rest axial travel `Delta x` completed in `T` using a triangular velocity profile gives `|xddot| = 4 Delta x/T^2`. A secondary speed change `Delta n` in the same duration gives `|omega_dot| = (2 pi/60)|Delta n|/T`.

For the straight helix, `Pi_s,c=0`. The script reports `Pi_s,omega` and `Pi_s,x` separately and their sum only as a worst-reinforcing sensitivity bound. It is **not** a claimed measured Sidewinder event.
