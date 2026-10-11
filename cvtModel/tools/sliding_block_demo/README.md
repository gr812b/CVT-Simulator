# Fixed-orientation sliding-block centrifugal actuator — research demo

This is a **standalone geometry and admissibility prototype**, not yet wired into CINDER's production force solver. It tests whether a symmetric set of non-rotating weights between two nominally active, frictionless ramp contacts can be reduced to the **two inertia functions and their derivatives** specified by `CINDER_General_Centrifugal_Mechanisms_v4.pdf` (2026-10-09).

The source uses **total weight-set mass `total_mass`** throughout. `display_count` is for reporting per-weight loads and showing representative hardware only; it never multiplies the physics. If all weights have the same pose and shape, `m_one = total_mass/display_count`, and `J_C,total = total_mass*gyration_radius**2`. Changing inserts may change the gyration radius even at equal total mass.

## Run

From the repository's `cvtModel` directory, with Python 3.10+, NumPy and SciPy available. Matplotlib is required for all plots; Plotly is needed only when generating the optional HTML:

```bash
python -m pip install matplotlib
python -m pytest -q tools/sliding_block_demo/test_sliding_block.py
python -m tools.sliding_block_demo.demo --output sliding_block_outputs
# Optional self-contained interactive browser file (plotly only needed to *generate* it)
python -m pip install plotly
python -m tools.sliding_block_demo.demo --output sliding_block_outputs --html
```

The command writes five PNG reports and, with `--html`, an offline `sliding_block_explorer.html`. Open the HTML directly in a browser. It has sliders for sheave closure, shaft RPM, an **imposed** shift acceleration and velocity, and **total** weight mass. It draws a **patent-inspired primary cross-section** with a fixed sheave, axially translating movable sheave, reaction cup, simplified spring, and reference belt trapezoid. Overlaid in prominent colors are the **actual solved** 2-D tracks, flyweight shape and position, contact points, reaction directions, and COM path. The four inertia functions and admissibility map remain available in the companion panels. **It does not solve a CINDER transient or engine response.**

**Geometry fidelity:** the supporting sheaves, housing, spring and belt wedge are intentionally stylized **visual context**; their outlines and belt position are not read from CVTech CAD and are not contact constraints in this prototype. Only the colored track profiles and computed weight pose enter the solver. The slider changes the moving ramp's axial position by the specified closure while the other profile remains fixed. This viewer must not be used to measure sheave clearances or belt seating; contact admissibility pertains exclusively to the two solved weight contacts.

To alter actual mechanisms without modifying code:

```bash
python -m tools.sliding_block_demo.demo --write-example-config weight.json
# Edit weight.json: total_mass, gyration_radius, and any face/track slopes,
# curvatures, radii, profile extents or sheave travel; keep all dimensions SI.
python -m tools.sliding_block_demo.demo --config weight.json --output my_weight_demo --html
```

The JSON has four independent `Profile` objects: `lower_track`, `upper_track`, `lower_face`, `upper_face`, each a line, quadratic, or unrotated circular arc **as an axial-height graph over radial position**. The tracks and weight faces can both be curved. All profiles require explicit valid intervals. `lower_track` stays fixed axially, `upper_track` moves by `+x`, and the block translates `(r(x), z(x))` without tilting. Other actuator layouts need their own sign/coordinate mapping. Production measured track offsets must be preserved. Optional `calibrate_at_zero:true` merely chooses offsets so both example contacts touch at `(r_ref, z=0, x=0)`; **do not enable that on measured geometry**.

### Model equations

For the whole identical weight set of total mass `M` and centroidal shaft-axis gyration radius `k_g`:

```
M_f(x)  = M [(dr/dx)^2 + (dz/dx)^2]
M_f'(x) = 2 M [(dr/dx)(d²r/dx²) + (dz/dx)(d²z/dx²)]
J_f(x)  = M [r(x)^2 + k_g^2]
J_f'(x) = 2 M r(x) (dr/dx)
```

The contact solver finds **global signed clearance minima over each finite block face**; two zero clearances determine `r,z`. Minimization also finds the material contact points and local slopes. Differentiating the active gap constraints yields `dr/dx = 1/(s_lower-s_upper)` and `dz/dx = s_lower dr/dx`. Curvature, including changing material contact locations on both weight and track, supplies second derivatives. This is precisely the fixed-orientation, meridional, `B_f=0` special case of v4; other motions require the full rigid-body formulation and potentially a mixed inertia coefficient.

**Messick regression:** in the straight-ramp special case, both slopes are constant. Consequently `M_f'=0`, while the ideal centrifugal thrust is `0.5*J_f'*omega^2 = M*r*(dr/dx)*omega^2`, which is Messick (2018), Eq. 9.2, with `M` replacing his `3m`. Note the **demo geometry and masses are illustrative**, not measurements of his machine or current CVTech production hardware.

## What PASS actually means

At each `x`, the prototype checks:

1. **Geometry:** both surfaces can touch without penetration **over the modeled face intervals** and neither extrapolates beyond its stated track domain.
2. **Unique local compatible motion:** the two gap gradients form a nonsingular/well-conditioned 2×2 Jacobian. The solver does **not** force singular branches through a fictitious clipped motion ratio.
3. **Unilateral contact feasibility for a specified operating point:** solve the rigid-block radial/axial Newton balance for total normal reactions. Both must be nonnegative. This check depends on **assumed** shaft speed, shift speed and shift acceleration. A negative normal means that the corresponding contact would have to pull the block: the ideal two-contact branch is impossible there.
4. **Consistency:** the moving ramp's axial reaction equals the v4 generalized force, and `(J_f')² <= 4 J_f M_f`.

The guide is assumed to prevent rotation and furnish whatever **tangential force and rocking moment** the motion requires. That required moment is calculated and reported, but **guide strength and guide contact loss are not tested** without guide geometry and capacity. Contacts at an explicit face endpoint are idealized as point/rounded-nose contact; an actual sharp corner has a contact normal cone that the simple profile does not resolve. No elastic deformation, friction, hysteresis, air gap, 3-D saddle geometry, floating sheave or discrete recontact impacts are included. Multiple possible geometric branches are not handled by a global branch/history solver; the sweep continues from the initial configuration and tests the chosen branch locally. The solver also does not yet certify absence of contact-mode changes between sample points or smoothness at every profile segment junction.

**PASS thus means 'locally admissible within the stated ideal model', not 'the actual CVTech clutch is validated'.** It does not guarantee robustness at impacts, bearing/guide strength, or global branch uniqueness.

## Illustrative cases and expected failures

| Scenario | Purpose | Expected result at 350 rad/s, 0 shift acceleration |
|---|---|---|
| `straight` | Linear tracks, fixed orientation; Messick exact limit | Valid along nominal travel |
| `curved-cup` | Circular track against straight opposing ramp | Valid; changing motion ratio |
| `both-curved` | Quadratic block faces against two quadratic tracks | Valid; contact locations move along faces |
| `short-track` | Same straight pair, but one short finite track | Valid initially; invalid past supported footprint |
| `parallel` | Two locally identical contact slopes | Singular at start; incompatible elsewhere |

In the browser, select `both-curved`, reduce RPM to 250, and increase the imposed `x¨` above ~200 m/s². One required normal becomes negative. Increase RPM instead and that same imposed acceleration may become admissible again. **Mass variation alone scales the ideal inertial contact demands; it does not change the sign of the contact normals in this purely inertial, frictionless probe.**

Additional checks in `test_sliding_block.py` cover analytic/finite-difference geometry derivatives, force equivalence under dynamic acceleration, the exact v4 energy identity, count invariance, proportional mass scaling, geometric singularity, track exhaustion and unilateral liftoff.

## Next gate before production CINDER use

Obtain measured weight *and guide* geometry (especially the actual contact edges), determine whether the real 3-D contact reduces to smooth 2-D effective profiles, trace reachable contact branches, and add guide and contact-mode validation. Only after that should this compiler be treated as a trustworthy source of four inertia maps for a specific installed CVTech tuning.
