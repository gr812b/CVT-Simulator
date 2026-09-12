# OTS Sidewinder helix-angle search — 2026-09-10

Purpose: check whether commercially available Sidewinder secondary hardware uses a materially smaller helix angle than the 31 deg YSR straight case, and whether this could move the helix motion ratio closer to the frozen Baja value.

## Stocked / pre-programmed Sidewinder options found

Dalton YSR catalogue:
- lowest straight listed angle: **31 deg** (`YSR 31`);
- lowest listed angle anywhere in a standard progressive cut: **28 deg**, as `YSR 36/28`;
- other low terminal angles include `40/30`, `39/31`, `46/32`, etc.;
- Dalton says individual custom angles are no longer supplied for this helix family outside volume special orders.

STM stock-Sidewinder helix catalogue:
- stocked choices found start at `33/38 deg` and `34 deg`;
- STM separately offers a custom-angle option, so lower angles can be manufactured, but those are not treated here as a standard OTS catalogue configuration.

A genuine E-Z-GO complete 28 deg driven clutch also exists commercially. It is useful context showing that 28 deg torque-reactive ramps are not unusual, but its application and mass scale are much smaller than the Sidewinder and it is not the chosen high-dynamic anchor.

## Motion-ratio comparison

Using the CINDER straight-helix relation

\[
H=\frac{1}{r_h\tan\alpha},
\]

the frozen Baja secondary has

\[
H_{\rm Baja}\approx61.81\ \mathrm{rad/m}
\]

from `r_h = 44.45 mm`, `alpha = 20 deg`.

To equal that motion ratio:
- a 31 deg helix would need `r_h ≈ 26.9 mm`;
- a 28 deg helix would need `r_h ≈ 30.4 mm`.

Therefore the currently assumed Sidewinder roller-track range of 45–60 mm gives a lower `H` than Baja even at 28 deg. The commercial case becomes more inertially significant mainly through its larger estimated movable-member MOI.

## Reflected-inertia consequence under present estimates

For the current high estimate `I_s,M ≈ 0.02047 kg m^2`, `r_h = 45 mm`:
- YSR31 local straight value: `M_ref ≈ 28.0 kg ≈ 2.92x Baja`;
- YSR36/28 local 28 deg segment: `M_ref ≈ 35.75 kg ≈ 3.72x Baja`.

With the same high MOI at 28 deg:
- `4x Baja` would require `r_h ≈ 43.4 mm`;
- `5x Baja` would require `r_h ≈ 38.8 mm`.

Those radii are not currently sourced, so >3.72x should be treated as plausible sensitivity, not a hardware-supported estimate, until the effective roller-track radius is measured.

## Sources

See `source_register.json` for exact URLs and authority classification. The key catalogue sources are Dalton YSR and STM Sidewinder stock-secondary helixes.
