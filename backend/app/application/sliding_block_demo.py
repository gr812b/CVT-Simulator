"""One representative assembly. CINDER owns all block/contact motion.

Cup/sheave backing is illustrative hardware material outside the contact
profiles. The block has a circular cup face and a flat face parallel to the
movable ramp. Its smooth section defines the uniform-steel mass properties;
the displayed polygon tessellates that section. This is a held-position
geometry study, not a compiled sliding-block simulation component.
"""

from functools import lru_cache
from math import pi, sqrt, tan

import cinder
import numpy as np
from cinder.model.cvt.actuation import (
    SlidingBlockGeometry,
    SlidingBlockMass,
    SlidingBlockProfile as Profile,
    SlidingBlockSpec,
)
from cinder.model.cvt.actuation.sliding_block_geometry import Mechanism, calibrate_zero, evaluate
from shapely.geometry import Polygon
from shapely.ops import unary_union
from scipy.integrate import quad

from app.schemas.sliding_block_demo import (
    SlidingBlockDemoFrame,
    SlidingBlockDemoResponse,
    SlidingBlockDemoInputs,
    SlidingBlockDemoField,
    SlidingBlockDimension,
    SlidingBlockFinding,
)

COUNT = 3
RPM = 2500.0
DEFAULT_INPUTS = SlidingBlockDemoInputs()
WIDTH = DEFAULT_INPUTS.block_width_m


class PreviewGeometryError(ValueError):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field


def input_fields():
    properties = SlidingBlockDemoInputs.model_json_schema()["properties"]
    return [
        SlidingBlockDemoField(
            key=key,
            label=p["title"],
            description=p["description"],
            feature=p["feature"],
            unit=p["unit"],
            minimum=p.get("minimum", p.get("exclusiveMinimum")),
            maximum=p.get("maximum", p.get("exclusiveMaximum")),
        )
        for key, p in properties.items()
    ]


def _translation_sweep(section, distance):
    """Polygon union swept by a pure axial translation, including edge strips."""
    moved = [(r, z + distance) for r, z in section]
    strips = [
        Polygon([a, b, (b[0], b[1] + distance), (a[0], a[1] + distance)])
        for a, b in zip(section, section[1:] + section[:1])
        if a[0] != b[0]
    ]
    return unary_union([Polygon(section), Polygon(moved), *strips])


def _block_mass(lower, upper, width=WIDTH, count=COUNT):
    """Integrate the smooth prism, independently of its display tessellation.

    Adaptive quadrature also handles arcs close to their open-semicircle limit.
    Moments use the local right-handed r,t,z frame.
    """

    def integrate(fun):
        return quad(
            lambda r: fun(r, lower.value(r), upper.value(r)),
            lower.left,
            lower.right,
            epsabs=1e-18,
            epsrel=1e-11,
            limit=100,
        )[0]

    area = integrate(lambda r, lo, hi: hi - lo)
    cx = integrate(lambda r, lo, hi: r * (hi - lo)) / area
    cz = integrate(lambda r, lo, hi: (hi**2 - lo**2) / 2) / area
    var_x = integrate(lambda r, lo, hi: r * r * (hi - lo)) / area - cx**2
    var_z = integrate(lambda r, lo, hi: (hi**3 - lo**3) / 3) / area - cz**2
    cov = integrate(lambda r, lo, hi: r * (hi**2 - lo**2) / 2) / area - cx * cz
    var_t = width**2 / 12
    return SlidingBlockMass(
        total_mass=7800 * area * width * count,
        count=count,
        com_offset=(float(cx), 0.0, float(cz)),
        centroidal_inertia_per_mass=(
            (var_t + var_z, 0.0, -cov),
            (0.0, var_x + var_z, 0.0),
            (-cov, 0.0, var_x + var_t),
        ),
    )


@lru_cache(maxsize=16)
def sample_definition(inputs=DEFAULT_INPUTS):
    half = inputs.block_span_m / 2
    origin = -0.4 * inputs.block_span_m
    radius = inputs.block_cup_radius_m
    if radius <= 0.9 * inputs.block_span_m:
        raise PreviewGeometryError(
            "The rounded-face radius must exceed 90% of the radial span for this arc construction.",
            "block_cup_radius_m",
        )
    # The datum is halfway through the block at local radial coordinate zero.
    offset = -inputs.block_thickness_m / 2 - (radius - sqrt(radius**2 - origin**2))
    lower = Profile("circle", origin, radius=radius, offset=offset, left=-half, right=half)
    # One slope is the source of truth for both mating flat faces.
    upper = Profile(
        "line",
        0,
        offset=inputs.block_thickness_m / 2,
        slope=-tan(inputs.ramp_angle_rad),
        left=-half,
        right=half,
    )
    # The difference of a line and this convex circle graph is concave:
    # its minimum thickness is at one of the two material endpoints.
    if min(upper.value(u) - lower.value(u) for u in (-half, half)) <= 0:
        raise PreviewGeometryError(
            "The block faces intersect. Increase datum thickness or reduce the ramp angle.",
            "block_thickness_m",
        )
    outline = [(float(r), lower.value(float(r))) for r in np.linspace(-half, half, 513)]
    outline += [(half, upper.value(half)), (-half, upper.value(-half))]
    mass = _block_mass(lower, upper, width=inputs.block_width_m)
    cup = Profile("circle", -0.03, radius=inputs.cup_radius_m, left=0.02, right=0.075)
    ramp = Profile("line", 0.052, slope=upper.slope, left=0.035, right=0.075)
    radial_min = max(0.05, ramp.left + half)
    radial_max = min(0.064, min(cup.right, ramp.right) - half)
    if not radial_min < 0.052 < radial_max:
        raise PreviewGeometryError(
            "The block footprint does not fit both finite tracks at the open reference radius. Reduce its radial span.",
            "block_span_m",
        )
    # Explicit synthetic assembly datum: both gaps close at (52 mm,0,0).
    # Never use this calibration to silently move measured user hardware.
    mechanism = calibrate_zero(
        Mechanism(
            cup,
            ramp,
            lower,
            upper,
            total_mass=mass.total_mass,
            gyration_radius=sqrt(mass.centroidal_inertia_per_mass[2][2]),
            display_count=COUNT,
            radius_ref=0.052,
            x_max=inputs.travel_m,
            com_offset=(mass.com_offset[0], mass.com_offset[2]),
        )
    )
    spec = SlidingBlockSpec(
        geometry=SlidingBlockGeometry(
            mechanism.lower_track,
            mechanism.upper_track,
            lower,
            upper,
            radial_min=radial_min,
            radial_max=radial_max,
            axial_position_min=0,
            axial_position_max=inputs.travel_m,
        ),
        mass=mass,
        guide="ideal_fixed_orientation",
    )
    return spec, outline, mechanism


@lru_cache(maxsize=16)
def preview(inputs=DEFAULT_INPUTS) -> SlidingBlockDemoResponse:
    spec, outline, mechanism = sample_definition(inputs)
    g = spec.geometry
    cup_inner = [(float(r), g.lower_track.value(float(r))) for r in np.linspace(0.02, 0.075, 1025)]
    cup_section = cup_inner + [(r, z - inputs.cup_backing_m) for r, z in reversed(cup_inner)]
    # A sleeve connects the cup to the shaft; all extra material belongs to
    # CVT hardware. The modelled track and the block faces are unmodified.
    cup_section += [(0.009, cup_inner[0][1] - inputs.cup_backing_m), (0.009, cup_inner[0][1])]
    half_angle = 20 * pi / 180

    def cone(r):
        return 0.072 - tan(half_angle) * (r - 0.018)

    moving_section = [
        (0.016, -0.025),
        (0.02, -0.025),
        (0.02, g.upper_track.value(0.02)),
        (0.095, g.upper_track.value(0.095)),
        (0.095, cone(0.095)),
        (0.02, cone(0.02)),
        (0.016, cone(0.02)),
    ]
    fixed_section = [
        (0.009, 0.087),
        (0.02, 0.087 + tan(half_angle) * 0.002),
        (0.095, 0.087 + tan(half_angle) * 0.077),
        (0.095, 0.092 + tan(half_angle) * 0.077),
        (0.009, 0.097),
    ]
    frames = []
    cup_solid, fixed_solid, moving_solid = map(
        Polygon, (cup_section, fixed_section, moving_section)
    )
    if not all(s.is_valid and s.area > 0 for s in (cup_solid, fixed_solid, moving_solid)):
        raise PreviewGeometryError(
            "The rear ramp crosses the sheave's belt-facing cone or creates an invalid body. Reduce block thickness or ramp angle.",
            "block_thickness_m",
        )
    # Exact translation sweep of the polygon section, not a frame-only check.
    sweep = _translation_sweep(moving_section, inputs.travel_m)
    pairs = [
        ("cup_moving", cup_solid, sweep),
        ("cup_fixed", cup_solid, fixed_solid),
        ("moving_fixed", sweep, fixed_solid),
    ]
    findings = []
    touching_thickness = inputs.block_thickness_m - (
        g.upper_track.value(g.lower_track.right) - g.lower_track.value(g.lower_track.right)
    )
    for name, a, b in pairs:
        if a.intersection(b).area > 1e-12 or a.distance(b) < 1e-8:
            if name == "cup_moving":
                message = f"The reaction cup interferes with the movable sheave. For this cup and ramp, datum thickness must exceed {touching_thickness * 1000:.2f} mm to clear the cup rim; add clearance beyond touching."
                field = "block_thickness_m"
            else:
                message = "The hardware interferes during the stroke. Reduce travel or adjust the block/cup dimensions."
                field = "travel_m"
            findings.append(
                SlidingBlockFinding(code=name + "_interference", field=field, message=message)
            )
    omega = RPM * 2 * pi / 60
    guess = (mechanism.radius_ref, 0.0)
    for x in np.linspace(0, inputs.travel_m, 241):
        x = float(x)
        # CINDER's finite-profile inspection solves the gaps and canonical
        # four-map force. Its strict simulation compiler rejects conformal
        # faces. Force resultants are unique here; pressure location and the
        # guide couple are not. Discard its arbitrary endpoint representative
        # and contact-only moment; neither is a physical prediction.
        p = evaluate(mechanism, x, omega=omega, guess=guess)
        if not p.admissible:
            raise PreviewGeometryError(
                f"Contact cannot be maintained at {x * 1000:.2f} mm closure. Adjust the rounded face, cup radius or stroke. {'; '.join(p.issues)}",
                "travel_m",
            )
        if p.lower.mode != "interior tangent":
            raise PreviewGeometryError(
                f"The rounded face runs out of interior cup contact at {x * 1000:.2f} mm. Reduce its radius or stroke, or adjust the cup radius.",
                "block_cup_radius_m",
            )
        rd, zd = p.radial - spec.mass.com_offset[0], p.axial - spec.mass.com_offset[2]
        if not g.radial_min <= rd <= g.radial_max:
            raise PreviewGeometryError(
                "Contact escaped the selected radial branch. Reduce the stroke.", "travel_m"
            )
        guess = (rd, zd)
        span = [
            (rd + u, zd + g.upper_face.value(u)) for u in (g.upper_face.left, g.upper_face.right)
        ]
        # Context belt section, seated between the two drawn 20-degree cones.
        outer_width, height = 0.028, 0.012
        inner_width = outer_width - 2 * tan(half_angle) * height
        inner_r = 0.018 + (inner_width - 0.015 + x) / (2 * tan(half_angle))
        outer_r = inner_r + height
        belt = [
            (inner_r, cone(inner_r) + x),
            (outer_r, cone(outer_r) + x),
            (outer_r, 0.087 + tan(half_angle) * (outer_r - 0.018)),
            (inner_r, 0.087 + tan(half_angle) * (inner_r - 0.018)),
        ]
        frames.append(
            SlidingBlockDemoFrame(
                closure_m=x,
                datum_m=(rd, zd),
                com_m=(p.radial, p.axial),
                fixed_contact_m=(p.lower.radial, p.lower.axial),
                moving_contact_span_m=span,
                fixed_normal=p.lower.normal,
                moving_normal=p.upper.normal,
                fixed_reaction_N=p.N_lower,
                moving_reaction_N=p.N_upper,
                closing_force_N=p.F_interface,
                belt_section_m=belt,
                interference_pairs=[
                    name
                    for name, a, b in (
                        ("cup_moving", cup_solid, Polygon([(r, z + x) for r, z in moving_section])),
                        ("cup_fixed", cup_solid, fixed_solid),
                        (
                            "moving_fixed",
                            Polygon([(r, z + x) for r, z in moving_section]),
                            fixed_solid,
                        ),
                    )
                    if a.intersection(b).area > 1e-12
                ],
            )
        )
    return SlidingBlockDemoResponse(
        sample_id="editable-rounded-block-v3",
        cinder_version=cinder.__version__,
        name="Sliding-block primary",
        description="Rounded cup face · matching flat ramp face",
        simulation_ready=False,
        inputs=inputs,
        fields=input_fields(),
        findings=findings,
        minimum_hardware_clearance_m=min(a.distance(b) for _, a, b in pairs),
        cup_touching_thickness_m=touching_thickness,
        dimensions=[
            SlidingBlockDimension(
                key="block_thickness_m",
                feature="block",
                attachment="block",
                points_m=((0, g.lower_face.value(0)), (0, g.upper_face.value(0))),
            ),
            SlidingBlockDimension(
                key="block_span_m",
                feature="block",
                attachment="block",
                points_m=(
                    (
                        -inputs.block_span_m / 2,
                        g.upper_face.value(-inputs.block_span_m / 2) + 0.006,
                    ),
                    (inputs.block_span_m / 2, g.upper_face.value(-inputs.block_span_m / 2) + 0.006),
                ),
            ),
            SlidingBlockDimension(
                key="block_cup_radius_m",
                feature="block",
                attachment="block",
                points_m=(
                    (g.lower_face.origin, g.lower_face.offset + g.lower_face.radius),
                    (0, g.lower_face.value(0)),
                ),
            ),
            SlidingBlockDimension(
                key="cup_radius_m",
                feature="cup",
                attachment="fixed",
                points_m=(
                    (g.lower_track.origin, g.lower_track.offset + g.lower_track.radius),
                    frames[0].fixed_contact_m,
                ),
            ),
            SlidingBlockDimension(
                key="cup_backing_m",
                feature="cup",
                attachment="fixed",
                points_m=(
                    (0.03, g.lower_track.value(0.03)),
                    (0.03, g.lower_track.value(0.03) - inputs.cup_backing_m),
                ),
            ),
            SlidingBlockDimension(
                key="ramp_angle_rad",
                feature="ramp",
                attachment="moving",
                points_m=((0.052, g.upper_track.value(0.052)), (0.072, g.upper_track.value(0.072))),
            ),
            SlidingBlockDimension(
                key="travel_m",
                feature="assembly",
                attachment="fixed",
                points_m=(
                    (0.013, g.upper_track.value(0.052)),
                    (0.013, g.upper_track.value(0.052) + inputs.travel_m),
                ),
            ),
        ],
        rpm=RPM,
        travel_m=inputs.travel_m,
        total_mass_kg=spec.mass.total_mass,
        block_count=COUNT,
        block_width_m=inputs.block_width_m,
        block_outline_m=outline,
        cup_section_m=cup_section,
        cup_track_m=cup_inner,
        moving_section_m=moving_section,
        moving_track_m=[
            (float(r), g.upper_track.value(float(r))) for r in np.linspace(0.035, 0.075, 33)
        ],
        fixed_section_m=fixed_section,
        shaft_radius_m=0.009,
        shaft_limits_m=(-0.07, 0.14),
        frames=frames,
    )
