# Sliding-block component records

Each JSON file is one `sliding_block_flyweight` component, to insert in a
pulley's `components` array. These are synthetic mechanisms, not measured
CVTech hardware. All distances are metres and mass is the complete set.

| Record | Contact construction | Axial interval |
| --- | --- | --- |
| `straight.json` | Original affine-track reference with endpoint contacts | 0–15 mm |
| `curved-cup.json` | Original circular cup example | 0–15 mm |
| `both-curved.json` | Original curved faces and tracks | 0–15 mm |
| `noncircular-cup.json` | User-defined quartic cup and matching flat upper faces | 0–12 mm |
| `multiple-contact.json` | Nonconvex lower face with two separated global contacts, plus matching flat upper faces | 0–15 mm |
| `changing-contact.json` | Flat block face crossing recessed cup material; contact spans change count | 0–23.4375 mm |
| `selected-branch.json` | Two possible assembled branches in a folded radial window; `reference_radius` selects the outer one | 0–2 mm |

The four user-defined/continuation records use uniform mass bodies integrated from their smooth block
faces, with 24 mm tangential width and 0.600 kg total across three blocks.
Their centroid and tensor are resolved data; changing the mass-body shape
requires recomputing them. The assigned total mass fixes effective density.
The contact definitions alone do not establish real guide capacity or whole
assembly clearance.

For the noncircular case the fixed track is
`f(r) = 0.8*(r-0.05) - 1e5*(r-0.05)^4`, with an axial datum offset chosen for
zero-closure contact. For the multiple-contact case the lower block face is
`b(u) = 0.8*u + 1e6*(u*u - 0.004**2)**2`. Its contacts against the affine cup
are `u = ±4 mm`; the intermediate material is separated from the cup.
The body datum follows `R = 0.05 + x/1.3`, `Z = 0.8*x/1.3`.
The COM adds the stored body-relative offset. Held clamping is therefore
`F = total_mass * COM_radius * omega**2 / 1.3`.

Matching flat upper faces determine clamping, with pressure-dependent ideal
guide-moment bounds. Inspect `u_intervals` and `guide_moment_bounds`; a geometric
representative contact point must not be displayed as a known pressure centroid.

In `changing-contact.json`, the lower envelope remains affine even while the
contact set changes. Contact positions are queried separately from the compiled
body motion. In `selected-branch.json`, the radial window contains a fold;
removing `reference_radius` reports the two possible assemblies. Both records
use an explicit axial datum so their travel starts at zero. They are examples
of the stated ideal model, not a pressure, interference or strength analysis.

See [the API guide](../../docs/SLIDING_BLOCK_FLYWEIGHT.md) for point input,
normalized polynomial segments, mass helpers and numerical diagnostics.
