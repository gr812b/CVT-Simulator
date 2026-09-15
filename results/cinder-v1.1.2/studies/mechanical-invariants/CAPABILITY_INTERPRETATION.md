# Mechanical-invariant capability interpretation — frozen working reference

The completed bilateral-reference audit establishes that all represented gross
tangential contact modes exist at deterministic admissible anchors, while the
size and persistence of those regimes are strongly asymmetric.

## Reference helix assumption

The v1.1.2 results reference model starts with a zero-clearance bilateral/slotted
secondary helix. Signed helix torque and axial-force mechanics are unchanged;
helix-flank selection is outside this belt/contact capability map.

The retained topology limits relevant here are:

- `T(l) >= 0`;
- `dN_j/dtheta >= 0`;
- `N_p, N_s >= 0`;
- static/kinetic traction admissibility and direction consistency;
- one global belt transport coordinate and fixed belt length;
- one gross traction state per wrap;
- remaining explicitly one-sided mechanism/travel-stop reactions.

## Top-level contact-domain picture

- Forward/reverse stick-stick and the common single-slip states are readily
  reproducible.
- Several kinetic branches are valid but naturally short-lived through restick
  or direction exchange.
- `secondary_slip_plus` is valid and reproducible but short-lived in its
  canonical state.
- `both_slip_mp` is valid but is the most extreme canonical quadrant found and
  has a very short initial branch.
- In several difficult states, local distributed wrap normal approaches zero
  while integrated pulley normal remains positive. Continuous full-wrap contact
  can therefore become the active limit before aggregate clamp force disappears.

## Assumption -> consequence map

| Retained assumption / reduction | Capability consequence |
|---|---|
| Single global belt transport coordinate `v_b` | Both pulley contacts must reconcile represented surface speeds through one belt speed. |
| Fixed belt length / no longitudinal strain state | No elastic strain reservoir or local creep wave can absorb incompatible local motion. |
| Taut flexible belt | `T < 0` ends the retained topology. |
| Prescribed continuous wrap | `dN/dtheta < 0` means local lift-off / a changed contact arc would be required. |
| One gross traction state per pulley wrap | Spatial stick/slip subregions are not represented. |
| Representative secondary contact / shared face reduction | Face-resolved velocity and torque-sharing differences are collapsed into one secondary state. |
| Bilateral reference helix | Signed torque reaction remains while helix-flank selection is outside the belt-domain map. |

If a stronger quantitative broad/constrained/extreme claim is later useful, use
a common local-neighbourhood perturbation study around the ten canonical contact
states rather than expanding the mechanical-invariants PASS gate.

The shared defaults retain deterministic reproduction anchors for
`secondary_slip_plus_exploration_full_pass_2535` and
`both_slip_mp_exploration_full_pass_3951`.
