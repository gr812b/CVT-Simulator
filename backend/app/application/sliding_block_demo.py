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

from app.schemas.sliding_block_demo import (
    SlidingBlockDemoFrame,
    SlidingBlockDemoResponse,
)

TRAVEL = 0.015
WIDTH = 0.024
COUNT = 3
RPM = 2500.0
RAMP_SLOPE = -0.5


def _block_mass(lower, upper, width=WIDTH, count=COUNT):
    """Integrate the smooth prism, independently of its display tessellation.

    Gaussian quadrature resolves these analytic profiles to floating-point
    precision. Moments use the local right-handed r,t,z frame.
    """
    nodes, weights = np.polynomial.legendre.leggauss(96)
    half = (lower.right - lower.left) / 2
    r = (lower.left + lower.right) / 2 + half * nodes
    lo, hi = (np.array([face.value(float(u)) for u in r]) for face in (lower, upper))

    def integrate(values):
        return float(half * (weights @ values))

    area = integrate(hi - lo)
    cx = integrate(r * (hi - lo)) / area
    cz = integrate((hi**2 - lo**2) / 2) / area
    var_x = integrate(r**2 * (hi - lo)) / area - cx**2
    var_z = integrate((hi**3 - lo**3) / 3) / area - cz**2
    cov = integrate(r * (hi**2 - lo**2) / 2) / area - cx * cz
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
def sample_definition():
    lower = Profile("circle", -0.008, radius=0.020, offset=-0.0125, left=-0.01, right=0.01)
    # One slope is the source of truth for both mating flat faces.
    upper = Profile("line", 0, offset=0.0125, slope=RAMP_SLOPE, left=-0.01, right=0.01)
    outline = [(float(r), lower.value(float(r))) for r in np.linspace(-0.01, 0.01, 513)]
    outline += [(0.01, upper.value(0.01)), (-0.01, upper.value(-0.01))]
    mass = _block_mass(lower, upper)
    cup = Profile("circle", -0.03, radius=0.125, left=0.02, right=0.075)
    ramp = Profile("line", 0.052, slope=RAMP_SLOPE, left=0.035, right=0.075)
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
            x_max=TRAVEL,
            com_offset=(mass.com_offset[0], mass.com_offset[2]),
        )
    )
    spec = SlidingBlockSpec(
        geometry=SlidingBlockGeometry(
            mechanism.lower_track,
            mechanism.upper_track,
            lower,
            upper,
            radial_min=0.05,
            radial_max=0.064,
            axial_position_min=0,
            axial_position_max=TRAVEL,
        ),
        mass=mass,
        guide="ideal_fixed_orientation",
    )
    return spec, outline, mechanism


@lru_cache(maxsize=1)
def preview() -> SlidingBlockDemoResponse:
    spec, outline, mechanism = sample_definition()
    g = spec.geometry
    cup_inner = [(float(r), g.lower_track.value(float(r))) for r in np.linspace(0.02, 0.075, 1025)]
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
    guess = (mechanism.radius_ref, 0.0)
    for x in np.linspace(0, TRAVEL, 241):
        x = float(x)
        # CINDER's finite-profile inspection solves the gaps and canonical
        # four-map force. Its strict simulation compiler rejects conformal
        # faces. Force resultants are unique here; pressure location and the
        # guide couple are not. Discard its arbitrary endpoint representative
        # and contact-only moment; neither is a physical prediction.
        p = evaluate(mechanism, x, omega=omega, guess=guess)
        if not p.admissible:
            raise ValueError(f"Invalid sample at {x:g}: {p.issues}")
        rd, zd = p.radial - spec.mass.com_offset[0], p.axial - spec.mass.com_offset[2]
        if not g.radial_min <= rd <= g.radial_max:
            raise ValueError("Sample escaped its selected radial branch")
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
            )
        )
    return SlidingBlockDemoResponse(
        sample_id="rounded-block-matched-ramp-v2",
        cinder_version=cinder.__version__,
        name="Sliding-block primary",
        description="Rounded cup face · matching flat ramp face",
        simulation_ready=False,
        rpm=RPM,
        travel_m=TRAVEL,
        total_mass_kg=spec.mass.total_mass,
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
