"""Physical oracles built from Cartesian material-point motion, not map formulas.

These checks verify the retained ideal branch, not the capacity of an actual
guide. The last test deliberately demonstrates information missing from the
current scalar mass specification.
"""
from dataclasses import replace
from itertools import product
from math import sqrt

import numpy as np
import pytest

from .scenarios import make
from .sliding_block import evaluate


def _particles(mechanism):
    # Eight equal masses, centred on the radial plane. Their actual second
    # moment matches the configured gyration radius; I_rz = I_tz = 0.
    radial_half, axial_half = 0.002, 0.004
    tangential_half = sqrt(mechanism.gyration_radius**2 - radial_half**2)
    return np.array(list(product(
        (-radial_half, radial_half),
        (-tangential_half, tangential_half),
        (-axial_half, axial_half),
    )))


def _positions(mechanism, particles, x, theta):
    pose = evaluate(mechanism, x, omega=0)
    assert pose.lower is not None and pose.upper is not None, pose.status
    c, s = np.cos(theta), np.sin(theta)
    rotation = np.array(((c, -s, 0), (s, c, 0), (0, 0, 1)))
    return (particles + (pose.radial, 0, pose.axial)) @ rotation.T


def particle_balance(mechanism, x, omega, alpha, xdot, xddot, *, h=1e-4):
    """Finite-difference material trajectories; sum Newton's force and moment.

    Only solved *positions* are reused. Map derivatives, contact normals, the
    four inertia quantities and the implementation's force law are not used by
    this oracle. The five-point time stencil limits rotation truncation error.
    """
    particles = _particles(mechanism)
    positions = {
        i: _positions(
            mechanism, particles, x + xdot*i*h + 0.5*xddot*(i*h)**2,
            omega*i*h + 0.5*alpha*(i*h)**2,
        ) for i in (-2, -1, 0, 1, 2)
    }
    velocity = (positions[-2] - 8*positions[-1] + 8*positions[1] - positions[2])/(12*h)
    acceleration = (-positions[2] + 16*positions[1] - 30*positions[0]
                    + 16*positions[-1] - positions[-2])/(12*h*h)
    dx = 2e-5
    virtual_motion = (_positions(mechanism, particles, x+dx, 0)
                      - _positions(mechanism, particles, x-dx, 0))/(2*dx)
    particle_mass = mechanism.total_mass/len(particles)
    return {
        "force": -particle_mass*np.sum(acceleration*virtual_motion),
        "torque": -particle_mass*np.sum(np.cross(positions[0], acceleration)[:, 2]),
        "energy": 0.5*particle_mass*np.sum(velocity**2),
    }


@pytest.mark.parametrize("name", ["straight", "curved-cup", "both-curved"])
@pytest.mark.parametrize("omega,alpha,xdot,xddot", [
    (280.0, 130.0, 0.11, -8.0),
    (-210.0, -85.0, -0.07, 5.0),
    (0.0, 0.0, 0.12, 4.0),
])
def test_cartesian_particle_force_torque_and_energy(name, omega, alpha, xdot, xddot):
    mechanism = make(name)
    x = 0.0075
    point = evaluate(mechanism, x, omega=omega, alpha=alpha, xdot=xdot, xddot=xddot)
    oracle = particle_balance(mechanism, x, omega, alpha, xdot, xddot)
    # Small absolute floor covers the nested contact-position solve in the
    # finite-difference acceleration, especially the low-force nonspinning case.
    assert point.F_interface == pytest.approx(oracle["force"], rel=2e-4, abs=3e-3)
    torque = -point.J_f*alpha - point.J_f_prime*xdot*omega
    assert torque == pytest.approx(oracle["torque"], rel=2e-4, abs=3e-5)
    energy = 0.5*point.M_f*xdot**2 + 0.5*point.J_f*omega**2
    assert energy == pytest.approx(oracle["energy"], rel=2e-5, abs=1e-7)


def test_straight_wedge_requires_a_guide_couple_even_at_steady_speed():
    # Independent hand FBD at x=7.5 mm, omega=350 rad/s:
    # R=(57 mm,3 mm); lower contact u=+5 mm, upper contact u=-5 mm.
    # Their local axial offsets are -9.25 mm and +15.75 mm.
    # Lower slope=1, upper=-1.5.
    # Axial balance gives equal axial contact forces F. Radial balance
    # gives (1+1.5)*F=M*r*omega^2. Contact moments do not cancel.
    m, r, omega = 0.75, 0.057, 350.0
    force = m*r*omega**2/2.5
    lower_force = np.array((-force, force))
    upper_force = np.array((-1.5*force, -force))
    lower_arm = np.array((0.005, -0.00925))
    upper_arm = np.array((-0.005, 0.01575))
    cross = lambda arm, load: arm[0]*load[1]-arm[1]*load[0]
    required_couple = -cross(lower_arm, lower_force)-cross(upper_arm, upper_force)
    point = evaluate(make("straight"), 0.0075, omega=omega)
    assert force == pytest.approx(2094.75)
    assert required_couple == pytest.approx(-51.05953125)
    assert point.guide_rocking_moment == pytest.approx(required_couple)
    assert point.admissible  # Conditional on an ideal orientation constraint.


def test_centroid_offset_can_break_the_zero_mixed_inertia_assumption():
    # Fixed orientation alone is insufficient. Hold the shaft still and move
    # a COM that is 2 mm off its guide's radial centreplane outwards.
    m, r, y, rp, zp = 0.75, 0.057, 0.002, 0.4, 0.4
    position = np.array((r, y, 0.003))
    unit_shift_velocity = np.array((rp, 0, zp))
    angular_momentum = m*np.cross(position, unit_shift_velocity)[2]
    assert angular_momentum == pytest.approx(-0.0006)
    # The current centred specification would return zero for this coefficient.
    # A future arbitrary-body importer must reject or retain this mixed term.


def test_compressive_running_contacts_do_not_guarantee_a_feasible_stop_impulse():
    mechanism = make("straight")
    point = evaluate(mechanism, mechanism.x_max, omega=350, xdot=0.1)
    assert point.admissible
    # Impose a stop from +0.1 m/s to rest with no shaft-speed jump. If BOTH
    # contacts were retained, the COM impulse would be M*q'*(0-0.1).
    # Independent unnormalised directions for the straight example are
    # (-1,+1) and (-1.5,-1). Use their unit normals to resolve impulse.
    normals = np.column_stack((np.array((-1, 1))/sqrt(2),
                               np.array((-1.5, -1))/sqrt(3.25)))
    momentum_change = 0.75*np.array((0.4, 0.4))*(-0.1)
    impulses = np.linalg.solve(normals, momentum_change)
    assert impulses == pytest.approx((-0.00848528137423857, 0.043266615305567875))
    assert impulses[0] < 0 < impulses[1]
    # Thus this imposed reset cannot preserve the two unilateral contacts.
    # A production adapter must reject it or resolve a new contact topology.


def test_identical_four_maps_do_not_determine_full_guide_moment():
    mechanism = make("straight")
    point = evaluate(mechanism, 0.0075, omega=350)
    a, b = 0.002, 0.004
    c = sqrt(mechanism.gyration_radius**2-a*a)
    # These equal-mass point sets share their COM, M, and I_zz. Reversing the
    # r-z correlation reverses I_rz while leaving all four map values unchanged.
    moments = []
    energies = []
    for correlation in (-1, 1):
        offsets = np.array([(sign*a, side*c, correlation*sign*b)
                            for sign, side in product((-1, 1), repeat=2)])
        masses = mechanism.total_mass/len(offsets)
        positions = offsets + (point.radial, 0, point.axial)
        acceleration = -350**2*positions.copy()
        acceleration[:, 2] = 0
        moments.append(masses*np.sum(np.cross(offsets, acceleration)[:, 1]))
        velocities = np.cross(np.array((0, 0, 350)), positions)
        energies.append(0.5*masses*np.sum(velocities**2))
    assert energies[0] == pytest.approx(energies[1])
    assert energies[0] == pytest.approx(0.5*point.J_f*350**2)
    assert moments == pytest.approx([0.735, -0.735])
    # Missing transverse inertial moment changes the actual required guide
    # couple; this is a documented diagnostic limitation, not a map failure.


@pytest.mark.parametrize("field", ["total_mass", "gyration_radius", "radius_ref", "x_max"])
@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_nonfinite_mechanism_inputs_are_rejected(field, value):
    with pytest.raises(ValueError, match="finite"):
        replace(make("straight"), **{field: value})


@pytest.mark.parametrize("field", ["origin", "offset", "slope", "curvature", "radius", "left", "right"])
def test_nonfinite_profile_inputs_are_rejected(field):
    with pytest.raises(ValueError, match="finite"):
        replace(make("straight").lower_track, **{field: float("nan")})


@pytest.mark.parametrize("field", ["omega", "alpha", "xdot", "xddot"])
def test_nonfinite_operating_state_cannot_pass(field):
    point = evaluate(make("straight"), 0.0075, **{field: float("nan")})
    assert not point.admissible
    assert "non-finite" in point.status


@pytest.mark.parametrize("count", [True, 1.5, 0])
def test_block_count_is_a_positive_integer(count):
    with pytest.raises(ValueError):
        replace(make("straight"), display_count=count)
