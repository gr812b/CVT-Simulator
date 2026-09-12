# Mechanical-invariant capability interpretation — working reference

This document records the interpretation we want the operating-domain study to
support. It is intentionally stronger than a green/red coverage matrix but is
**not yet manuscript wording**.

## What the study is trying to establish

CINDER's selling point is that it is a dynamic initial-value model rather than a
single prescribed shift trajectory. The useful claim is therefore not that
"every mathematically imaginable state works." It is that the model can begin
from and evolve through a very broad set of **physically admissible states
inside its retained topology**, while detecting when the assumptions that define
that topology stop being possible.

The final results should distinguish three questions:

1. **Does the requested gross contact topology exist in the retained model?**
2. **How broad or narrow is the admissible neighbourhood of that topology?**
3. **When the neighbourhood ends, which retained assumption/inequality ends it?**

The mechanical-invariants PASS answers the first question at deterministic
anchors. The planned capability refinement answers the second and third.

## Results reference helix

General v1.1.2 result studies use a zero-clearance bilateral/slotted secondary
helix. The signed production helix torque and axial force equations are
unchanged; only the one-selected-flank compression inequality is removed. This
prevents a hardware-specific flank lift-off from obscuring the belt/contact
questions being stressed here. Unilateral-versus-slotted behavior belongs in a
separate topology study.

Accordingly, the following remain genuine retained-topology limits in the
mechanical-invariant capability map:

- `T(l) >= 0`: the modeled belt is taut and cannot carry compression;
- `dN_j/dtheta >= 0`: the prescribed continuous wrap cannot require tensile
  normal contact;
- `N_p, N_s >= 0`;
- static/kinetic traction admissibility and direction consistency;
- the one-transport-coordinate, fixed-length kinematics;
- one gross traction state per wrap;
- any *other* explicitly unilateral mechanism or travel-stop reaction.

A negative tension or distributed normal load is therefore not "negative belt
physics" to clip away. It means the assumed taut/full-wrap topology has ended.
A real CVT might continue by slackening, partial lift-off, changed wrap,
elastic creep/redistribution, or other omitted topology.

## Current top-level picture from the completed exploration

The missing-coverage exploration established that all four both-slip quadrants
and both signed single-interface slip directions are **possible** under the
retained equations. The awkward classes were search/domain issues, not proof of
physical impossibility.

Preliminary qualitative map:

- **Routine / broad candidates:** forward stick-stick, reverse stick-stick,
  primary slip in both directions, free upshift/backshift, static rest, and the
  structural boundary transitions were found without special rare-state
  construction.
- **Valid but often transient:** several kinetic branches leave their initial
  topology quickly through restick or direction exchange. Short dwell is not a
  failure; it is hybrid dynamics and should be reported as such.
- **Secondary-slip positive:** valid, but the exploration needed a targeted
  state and showed a strong tendency for the positive secondary relative speed
  to accelerate back toward zero.
- **Both-slip (-,+):** valid but the hardest gross quadrant found so far. The
  admissible region was narrow in the exploratory search, and neighbouring
  candidates commonly lost belt tension or primary distributed wrap contact.
  The successful anchor is therefore a stress-state reproduction point, not a
  claim that this is a normal Baja operating condition.

The slotted reference topology should make those conclusions cleaner by
removing helix-flank lift-off as a competing termination mechanism.

## Assumption -> consequence map to preserve

| Retained assumption / reduction | Capability consequence |
|---|---|
| Single global belt transport coordinate `v_b` | Both pulley contacts must reconcile their represented surface speeds through one belt speed; unusual opposing-slip orderings can occupy a narrow state region. |
| Fixed belt length / no longitudinal strain state | No elastic strain reservoir or local creep wave can absorb incompatible local motion. |
| Taut flexible belt | `T < 0` is loss of the retained topology, not an allowed compressive belt state. |
| Prescribed continuous wrap | `dN/dtheta < 0` means local lift-off / shortened contact would be required, which this topology does not continue through. |
| One gross traction state per pulley wrap | Spatial stick/slip subregions and traction reversals within one wrap are not represented. |
| Representative secondary contact speed / shared face torque reduction | Face-resolved differences in fixed/movable sheave velocity and torque sharing are collapsed into one secondary contact state. |
| Rigid pulley / ideal mechanism geometry | Compliance/backlash that could soften or delay regime transitions is absent. |
| Bilateral results helix | Signed torque reaction remains, but helix-flank selection no longer limits the belt-domain study. |

The key interpretive sentence is: **inadmissible within CINDER's retained
belt/contact topology is not automatically impossible in real hardware.** It
means the real hardware would need a degree of freedom or contact topology that
this reduction intentionally omits.

## How to make the capability map publication-quality

Do not use raw random-search attempt count as the final measure of "easy" versus
"hard"; once a deterministic anchor is known, that number depends too much on
search ordering. Instead, center a common local perturbation cloud around each
canonical contact state and measure:

1. fraction for which the requested branch equations satisfy all physical
   inequalities when evaluated directly;
2. fraction for which the production classifier actually selects that same
   topology;
3. distribution of initial branch dwell time and first exit event;
4. distribution of the first failing physical condition (`T`, local `dN/dtheta`,
   resultant normal, traction capacity/direction, stop/mechanism constraint);
5. physical margin scales, not only normalized numerical guard ratios.

This creates a defensible continuum from **broad/easy** through
**valid-but-constrained** to **extreme/narrow**, and ties every label to a
specific retained assumption rather than solver folklore.

## Study cases considered frozen enough to reuse

The shared defaults own the common case vocabulary. The two previously missing
classes now also have deterministic reproduction anchors:

- `secondary_slip_plus_exploration_full_pass_2535`;
- `both_slip_mp_exploration_full_pass_3951`.

These anchors still have to pass the production classifier, full invariant
checks, hybrid continuation and exact successor audit on every study run. They
are not forced solutions.

Two additional states that previously terminated **only** on the unilateral
helix are retained as capability probes. Under the slotted reference topology,
they are useful checks that the helix hardware constraint has actually been
removed from the belt-domain question.
