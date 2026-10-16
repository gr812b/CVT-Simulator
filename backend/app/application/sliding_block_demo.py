"""One representative assembly. CINDER owns all block/contact motion.

Cup/sheave backing is illustrative hardware material outside the contact
profiles. The block is exactly the polygon between its two finite faces,
extruded to a declared width; its uniform-steel mass properties follow that
same solid. This is a held-position inspection, not an RPM-driven simulation.
"""

from functools import lru_cache
from math import pi, tan

import cinder
import numpy as np
from cinder.model.cvt.actuation import (
    SlidingBlockFlyweightForce,
    SlidingBlockGeometry,
    SlidingBlockMass,
    SlidingBlockProfile as Profile,
    SlidingBlockSpec,
)
from cinder.model.cvt.actuation.types import PulleyActuationContext
from cinder.model.cvt.closure import AffineClosureScalar

from app.schemas.sliding_block_demo import (
    SlidingBlockDemoFrame,
    SlidingBlockDemoResponse,
)

TRAVEL = 0.015
WIDTH = 0.024
COUNT = 3
RPM = 2500.0


def _block_mass(outline, width=WIDTH, count=COUNT):
    """Exact area moments of a uniform polygon prism, in the local r,t,z frame."""
    p = np.array(outline)
    q = np.roll(p, -1, axis=0)
    x, z, u, v = p[:, 0], p[:, 1], q[:, 0], q[:, 1]
    cross = x * v - u * z
    area = float(np.sum(cross) / 2)
    cx, cz = np.sum((p + q) * cross[:, None], axis=0) / (6 * area)
    var_x = float(np.sum((x * x + x * u + u * u) * cross) / (12 * area) - cx**2)
    var_z = float(np.sum((z * z + z * v + v * v) * cross) / (12 * area) - cz**2)
    cov = float(np.sum((2 * x * z + x * v + u * z + 2 * u * v) * cross) / (24 * area) - cx * cz)
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


@lru_cache(maxsize=1)
def sample_force():
    lower = Profile("line", 0, offset=-0.0125, slope=-0.35, left=-0.01, right=0.01)
    upper = Profile("line", 0, offset=0.0125, slope=-1.65, left=-0.01, right=0.01)
    outline = [
        (-0.01, lower.value(-0.01)),
        (0.01, lower.value(0.01)),
        (0.01, upper.value(0.01)),
        (-0.01, upper.value(-0.01)),
    ]
    cup = Profile("circle", -0.03, radius=0.125, left=0.02, right=0.075)
    # At zero closure the datum is (r,z)=(52 mm,0). Both finite-face
    # endpoint contacts follow directly from their slope inequalities.
    cup = Profile(
        "circle",
        -0.03,
        radius=0.125,
        offset=lower.value(0.01) - cup.value(0.062),
        left=0.02,
        right=0.075,
    )
    ramp = Profile("line", 0.042, offset=upper.value(-0.01), slope=-0.5, left=0.035, right=0.075)
    spec = SlidingBlockSpec(
        geometry=SlidingBlockGeometry(
            cup,
            ramp,
            lower,
            upper,
            radial_min=0.05,
            radial_max=0.064,
            axial_position_min=0,
            axial_position_max=TRAVEL,
            allow_end_contacts=True,
        ),
        mass=_block_mass(outline),
        guide="ideal_fixed_orientation",
    )
    return SlidingBlockFlyweightForce(spec), outline


@lru_cache(maxsize=1)
def preview() -> SlidingBlockDemoResponse:
    force, outline = sample_force()
    g = force.spec.geometry
    cup_inner = [(float(r), g.lower_track.value(float(r))) for r in np.linspace(0.02, 0.075, 257)]
    cup_section = cup_inner + [(r, z - 0.0035) for r, z in reversed(cup_inner)]
    # A sleeve connects the cup to the shaft; all extra material belongs to
    # CVT hardware. The modelled track and the block faces are unmodified.
    cup_section += [(0.009, cup_inner[0][1] - 0.0035), (0.009, cup_inner[0][1])]
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
    omega = RPM * 2 * pi / 60
    for x in np.linspace(0, TRAVEL, 241):
        x = float(x)
        p = force.inertia_map.pose(x)
        reactions = force.inertia_map.reactions(x, omega=omega, alpha=0, xdot=0, xddot=0)
        if not reactions.compressive:
            raise ValueError("Sample requires a tensile held-position contact")
        ctx = PulleyActuationContext(
            time=0,
            axial_position=x,
            axial_speed=0,
            shaft_speed=omega,
            axial_acceleration=AffineClosureScalar.constant(0),
        )
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
                datum_m=(p.datum_radial, p.datum_axial),
                com_m=(p.radial, p.axial),
                fixed_contact_m=(p.lower.radial, p.lower.axial),
                moving_contact_m=(p.upper.radial, p.upper.axial),
                fixed_normal=p.lower.normal,
                moving_normal=p.upper.normal,
                fixed_reaction_N=reactions.lower_normal,
                moving_reaction_N=reactions.upper_normal,
                closing_force_N=float(force.evaluate(ctx).bias),
                guide_moment_Nm=reactions.guide_moment,
                belt_section_m=belt,
            )
        )
    return SlidingBlockDemoResponse(
        sample_id="curved-cup-linear-ramp-v1",
        cinder_version=cinder.__version__,
        name="Sliding-block primary",
        description="Curved reaction cup · straight movable ramp",
        rpm=RPM,
        travel_m=TRAVEL,
        total_mass_kg=force.spec.mass.total_mass,
        block_count=COUNT,
        block_width_m=WIDTH,
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
