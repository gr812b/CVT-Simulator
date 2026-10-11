# Fixed-pivot flyweight through the four-inertia interface

This executable reference accompanies **Clamping Mechanism Implementations,
Part I: The Fixed-Pivot Roller Flyweight**, draft 1, October 9, 2026.

It constructs the finite-roller contact geometry, its analytic motion
derivatives, the flyweight mass moments, and the four returned values:

`M, dM/dx, J, dJ/dx`.

It is an engineering reference for the documented mechanism and branch, not
a production patch or a CVTech model. The general derivation and the
implementation document describe the assumptions and signs in full.

## Files

- `fixed_pivot_reference.py`: independent geometry, mass, maps, and optional
  cubic angle compilation. It does not import CINDER.
- `verify_reference.py`: analytic, direct-particle, derivative, contact,
  interpolation, and optional CINDER comparison checks.
- `check_results.json`: the recorded full comparison used in the document.

## Run

Requires Python 3.10 or newer, NumPy, and SciPy. The recorded run used
Python 3.12.14, NumPy 2.3.5, and SciPy 1.17.0.

```sh
python verify_reference.py --output independent_results.json
```

For the CINDER comparison, pass a local checkout whose `cvtModel` content
matches tag `cinder-v1.1.5`, commit
`8261226b8cd1e8b65c883d3a382c3f109ccbb10c`:

```sh
python verify_reference.py --repo /path/to/CVT-Simulator --output my_results.json
```

On Windows the repository path can be quoted in the usual way:

```powershell
python verify_reference.py --repo "F:\Code\Projects\CVT-Simulator" --output my_results.json
```

The script checks that the model source matches the pinned version, imports
that checkout, and does not edit it. A newer repository head is accepted when
its `cvtModel` content is unchanged. A default run without `--output` writes
`check_results.json` beside the script, so use a distinct name to retain the
included record.

## Scope of the implementation

The reference geometry solver uses the forward-arm branch (`a > 0`) with a
monotone contact-to-closure map. It checks its sampled branch coverage and
regularity and refuses extrapolation. These diagnostics do not replace the
production audit for arbitrary ramps, global interference, or branch
multiplicity. The reference fixture also passes CINDER's existing geometry
audit.

The profile is the v1.1.5 reference: 35 degrees over 5 mm, a 3 mm C3 blend,
then a 35-to-20-degree circular segment over 30 mm. These are profile-coordinate
spans. The manuscript's older provisional profile uses different angles.

The simplified mass model uses a uniform slender arm and a concentrated tip
package. Finite roller radius is retained geometrically; independent roller
spin and finite tip-component centroidal inertias are omitted. The four-map
reduction assumes no mixed shaft-shift kinetic term.

The CINDER interface comparison deliberately reuses the existing compiled
angle map. The independent exact-map comparison and the compiled-versus-exact
error check are separate. Their errors must not be conflated.

The tests establish agreement for the documented mechanics and sampled
software paths. They do not validate hardware dimensions, losses, contact
compliance, or a CVTech design.
