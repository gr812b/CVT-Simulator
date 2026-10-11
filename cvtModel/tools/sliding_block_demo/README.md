# Fixed-orientation sliding-block centrifugal actuator — research demo

This is a **standalone geometry and admissibility prototype**, not yet wired into CINDER's production force solver. It tests whether a symmetric set of non-rotating weights between two nominally active, frictionless ramp contacts can be reduced to the **two inertia functions and their derivatives** specified by `CINDER_General_Centrifugal_Mechanisms_v4.pdf` (2026-10-09).

The source uses **total weight-set mass `total_mass`** throughout. `display_count` is for reporting per-weight loads and showing representative hardware only; it never multiplies the physics. If all weights have the same pose and shape, `m_one = total_mass/display_count`, and `J_C,total = total_mass*gyration_radius**2`. Changing inserts may change the gyration radius even at equal total mass.

## Run

From the repository root (Python 3.10+):

```powershell
python -m pip install -r cvtModel/tools/sliding_block_demo/requirements-demo.txt
python -m pytest -q cvtModel/tools/sliding_block_demo
python -m cvtModel.tools.sliding_block_demo.demo --output sliding_block_outputs --html
```

Or, from `cvtModel`, use `python -m tools.sliding_block_demo.demo --html`.
Open `sliding_block_outputs/sliding_block_explorer.html` directly in a browser;
it is self-contained and makes no network requests. The command also writes five
PNG reports. Shapely is a **demo-only** dependency for checking the drawn solids;
the production CINDER package and its dependencies are unchanged.

The closure slider drives a single **meridional half-section**. Axial position
`z` is horizontal; radius `r` is vertical. The shaft axis is **r = 0**. The
spring's sectioned coils are symmetric about that axis, outside the shaft and
inside the hub bore. Its moving seat translates by exactly `+x`, so its seat
spacing decreases by `x`.

### How the section is built

- The cup, shaft and fixed sheave retain exactly the same coordinates throughout
  the sweep. The moving sheave, contact insert and spring seat translate rigidly
  by `+x`. Neither body changes shape to fit the current pose.
- Hatched regions are finite **material polygons**, with the original contact
  profiles forming their exposed faces. The block uses the original solved
  shape and pose. Contact points and reaction arrows use the same coordinate
  transformation as the solids.
- The old full mathematical track continuations crossed outside their used
  contact regions. They cannot all be material. For this **reference assembly**,
  each insert retains the profile over its swept contact band with a 1 mm radial
  margin, bounded by the original domain; unused extensions are relieved. These
  bands are chosen **once for the whole sweep**, not clipped at each position.
  The backings connect the inserts to the cup or moving sheave. This changes the
  supporting illustration, not `scenarios.py`, `sliding_block.py`, the active
  contact profiles, the motion, or the four inertia functions.
- The belt is a rigid 10 mm-deep trapezoid, 30 mm wide at its pitch line, between
  conical faces with a 20° half-angle. Both flanks seat on those faces. Its radius
  satisfies `r_b(x) = r_b(0) + x/(2*tan(20°))`; its axial center moves by `x/2`.
  Its dimensions and area remain constant, and the groove widens outward. Belt
  radius is **independent of the weight COM**, with no clamping or ad hoc offsets.
- `section.py` is the single source of coordinates for both PNGs and the HTML.
  The browser projects the exported solids and translates the moving assembly;
  it does not reconstruct a second set of approximate sheaves.

**Geometry fidelity:** the finite insert extents, backing solids, sheave cones,
shaft and spring are synthetic reference dimensions, not CVTech measurements.
Relieving unused extensions preserves the selected contact path but is not a
proof that a measured production part has this envelope. The original solver's
full-footprint domain restriction is retained even where the reference solid is
relieved. In particular, the short-track case is a **model domain limit**, not a
simulated weight falling off an actual measured rail. Spring forces, belt forces,
guide capacity and full 3-D clearances are not calculated.

The viewer reports **contact admissibility** and **reference-solid clearance**
separately. It checks that outlines are valid and that independent bodies do not
interpenetrate; a custom reference envelope that fails these checks is flagged.
Tiny curve-tessellation errors are bounded by a `0.0002 mm²` overlap-area
tolerance. These are checks of the sampled drawing, not continuous collision
certification. Contact vertices are retained exactly in the profile meshes.

A failed geometry solve can return a finite least-squares iterate. That iterate
is **not a compatible pose**: the viewer omits the weight and its COM at those
positions. A negative normal reaction is different: the compatible shape remains
visible with a red dashed outline and a liftoff warning. No subsequent free
motion or recontact is invented.

RPM, imposed acceleration/velocity, and **total** weight mass still control the
force/admissibility diagnostics. All five original sample mechanisms remain.
**The viewer does not solve a CINDER transient or engine response.**

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
| `short-track` | Same straight pair, but a restricted mathematical track domain | Valid initially; full block footprint later exceeds the domain |
| `parallel` | Two locally identical contact slopes | Singular at start; incompatible elsewhere |

In the browser, select `both-curved`, reduce RPM to 250, and increase the imposed `x¨` above ~200 m/s². One required normal becomes negative. Increase RPM instead and that same imposed acceleration may become admissible again. **Mass variation alone scales the ideal inertial contact demands; it does not change the sign of the contact normals in this purely inertial, frictionless probe.**

Additional checks in `test_sliding_block.py` cover analytic/finite-difference geometry derivatives, force equivalence under dynamic acceleration, the exact v4 energy identity, count invariance, proportional mass scaling, geometric singularity, track exhaustion and unilateral liftoff.

## Verification

```powershell
python -m pytest -q cvtModel/tools/sliding_block_demo
```

The original 11 mechanics tests are retained. `test_section.py` adds tests of
constant belt size and flank seating, rigid part translation, contacts on real
solid boundaries, spring clearance about r=0, all 76 frames of each sample,
intermediate positions, failure display, and detection of deliberately crossed
or overlapping material. It also checks that HTML uses the same coordinates as
the static renderer.

Optional real-browser checks and screenshots:

```powershell
python -m pip install playwright
python -m playwright install chromium
python -m cvtModel.tools.sliding_block_demo.check_browser sliding_block_outputs/sliding_block_explorer.html --screenshots sliding_block_outputs/browser_qa
```

This exercises open/middle/closed positions in all five examples, liftoff,
mass scaling, display toggles, fixed-body invariance, JavaScript errors and
mobile overflow. Review its screenshots as well as the numerical checks.

## Next gate before production CINDER use

Obtain measured weight *and guide* geometry (especially the actual contact edges), determine whether the real 3-D contact reduces to smooth 2-D effective profiles, trace reachable contact branches, and add guide and contact-mode validation. Only after that should this compiler be treated as a trustworthy source of four inertia maps for a specific installed CVTech tuning.
