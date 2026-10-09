# Centrifugal mechanism inertia boundary

CINDER's common centrifugal element consumes two functions of local sheave
closure and their derivatives. A mechanism supplies its compatible motion and
mass distribution; the common element supplies the resulting axial force,
shaft reaction, and kinetic modes.

The Python types live in `cinder.model.cvt.actuation`:

- `CentrifugalInertiaSample` holds one evaluation of the four quantities.
- `CentrifugalInertiaMap` declares the local travel interval and `evaluate(x)`.
- `CentrifugalInertiaForce` mounts that provider on either pulley.
- `FixedPivotFlyweightInertiaMap` adapts the existing fixed-pivot map.

## Quantities and retained mechanics

Here `x` increases in the local pulley-closing direction. Gradients are with
respect to that position, measured in metres.

| Sample field | Quantity | Units |
| --- | --- | --- |
| `effective_mass` | `M(x)` | kg |
| `effective_mass_gradient` | `dM/dx` | kg/m |
| `shaft_inertia` | `J(x)` | kg m² |
| `shaft_inertia_gradient` | `dJ/dx` | kg m |

The energy and reactions are

```text
T = 1/2 M x_dot² + 1/2 J omega²
F_closing = 1/2 J' omega² - M x_ddot - 1/2 M' x_dot²
T_shaft,reaction = -J alpha - J' x_dot omega
```

`PulleyActuationContext.axial_acceleration` supplies the complete affine local
acceleration. All its closure gains are multiplied by `-M`; the provider does
not choose or remap a shift column. The host's owning-shaft channel receives
the `-J` acceleration coefficient. The same `M` and `J` enter kinetic modes,
so continuous dynamics and event projection retain the same mechanism energy.

## Provider obligations

This boundary applies when the internal configuration is determined by `x`
and there is no mixed `B(x) omega x_dot` kinetic term. Additional internal
states or mixed coupling require a richer mechanical description.

`M` and `J` are finite, nonnegative C1 functions on the admitted branch. The
returned gradients must be their actual derivatives, evaluated from the same
motion representation. The sample validates finite values and nonnegative
inertias; it cannot prove smoothness or derivative consistency from one point.
Gradients can have either sign.

The provider declares a finite, ordered interval through `axial_position_min`
and `axial_position_max`. Assembly preflight and plant construction check that
this covers the pulley travel. The provider enforces its evaluation domain,
including its own documented endpoint roundoff policy.

Geometry, branch selection, and contact admissibility remain responsibilities
of the mechanism. The generic element does not infer a contact reaction from
the sign of its net force. Mechanisms with unilateral contacts must supply
their own contact policy through the existing actuator hook. Springs, losses,
and other loads remain separately composed elements. Mass included in `M` and
`J` must not also be included in the surrounding constant pulley inertias.

## Existing fixed-pivot implementation

The original configuration map still returns `q, q', q'', J, J', I` and keeps
its audited contact branch and compiled angle spline. The adapter evaluates
that map once and returns

```text
M  = I q'²
M' = 2 I q' q''
J  = original shaft inertia
J' = original shaft-inertia gradient
```

`FixedPivotFlyweightForce` uses the common evaluator with that adapter. Its
constructor, `.spec.mechanism_map`, contact check, numerical zero guard, and
inspection keys and labels remain available. The two kinetic modes are now
shaft rotation with coefficient `J` and local axial motion with coefficient
`M`; the resulting kinetic matrix equals the previous `J` and `I q'²` form.

Existing Python callers continue to construct `FixedPivotFlyweightForce` in
the same way. To inspect its new boundary directly:

```python
sample = fixed_pivot_force.inertia_map.evaluate(local_closure)
print(sample.effective_mass, sample.effective_mass_gradient)
print(sample.shaft_inertia, sample.shaft_inertia_gradient)
```

Saved fixed-pivot designs retain the `fixed_pivot_roller_flyweight` component
kind and the existing physical geometry and mass fields. This addition does
not introduce a JSON representation for arbitrary function providers. The
older simplified `CentrifugalRampForce` retains its existing approximation;
it is not silently given new shift-inertia terms.

The accompanying smoke tests compare the fixed-pivot equations, contact sign,
kinetic energy, coupled closure, and stop projection with the previous q/I
representation. A coefficient-only fixture checks the generic interface and
its power balance without depending on fixed-pivot fields. No additional
hardware mechanism is introduced in this first implementation.
