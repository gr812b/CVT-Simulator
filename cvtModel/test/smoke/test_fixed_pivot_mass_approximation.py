from __future__ import annotations

from math import isclose

from cinder.model.cvt.actuation import (
    ConcentratedTipHardwareMass,
    FlyweightMassGeometry,
)


def test_tip_hardware_factory_matches_declared_approximation() -> None:
    hardware = ConcentratedTipHardwareMass(
        roller_bearing_mass_per_flyweight=0.010,
        bolt_mass_per_flyweight=0.004,
        nut_washer_mass_per_flyweight=0.003,
        other_fixed_tip_hardware_mass_per_flyweight=0.002,
        tuning_mass_per_flyweight=0.110,
    )
    assert isclose(hardware.total_mass_per_flyweight, 0.129)

    length = 0.0315214
    arm_mass = 0.013646
    mass = FlyweightMassGeometry.uniform_slender_arm_with_concentrated_tip_hardware(
        number_of_flyweights=3,
        arm_length=length,
        arm_mass_per_flyweight=arm_mass,
        tip_hardware=hardware,
    )

    expected_first_u = arm_mass * length / 2.0 + 0.129 * length
    expected_second_u = arm_mass * length**2 / 3.0 + 0.129 * length**2
    assert isclose(mass.first_moment_u, expected_first_u)
    assert isclose(mass.second_moment_u, expected_second_u)
