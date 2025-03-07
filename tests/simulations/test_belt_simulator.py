import unittest
import sys
import os
import numpy as np

from simulations.belt_simulator import BeltSimulator
from utils.theoretical_models import TheoreticalModels as tm
from constants.constants import RUBBER_DENSITY

from constants.car_specs import (
    SHEAVE_ANGLE,
    BELT_CROSS_SECTIONAL_AREA,
    BELT_HEIGHT
)

class TestBeltSimulator(unittest.TestCase):
    def setUp(self):
        self.simulator_primary = BeltSimulator(μ_static=0.5, μ_kinetic=0.4, primary=True)
        self.simulator_secondary = BeltSimulator(μ_static=0.5, μ_kinetic=0.4, primary=False)

    def test_calculate_centrifugal_force_primary(self):
        ω = 100
        shift_distance = 0.1
        wrap_angle = np.pi / 2
        expected_radius = tm.outer_prim_radius(shift_distance) - BELT_HEIGHT / 2
        expected_length = expected_radius * wrap_angle
        expected_mass = RUBBER_DENSITY * BELT_CROSS_SECTIONAL_AREA * expected_length
        expected_force = tm.centrifugal_force(expected_mass, ω, expected_radius)
        result = self.simulator_primary.calculate_centrifugal_force(ω, shift_distance, wrap_angle)
        self.assertAlmostEqual(result, expected_force, places=5)

    def test_calculate_centrifugal_force_secondary(self):
        ω = 100
        shift_distance = 0.05
        wrap_angle = np.pi / 2
        expected_radius = tm.outer_sec_radius(shift_distance) - BELT_HEIGHT / 2
        expected_length = expected_radius * wrap_angle
        expected_mass = RUBBER_DENSITY * BELT_CROSS_SECTIONAL_AREA * expected_length
        expected_force = tm.centrifugal_force(expected_mass, ω, expected_radius)
        result = self.simulator_secondary.calculate_centrifugal_force(ω, shift_distance, wrap_angle)
        self.assertAlmostEqual(result, expected_force, places=5)

    def test_radial_force_from_clamping(self):
        clamping_force = 1000
        expected_force = 2 * clamping_force * np.tan(SHEAVE_ANGLE / 2)
        result = self.simulator_primary.radial_force_from_clamping(clamping_force)
        self.assertAlmostEqual(result, expected_force, places=5)

    def test_calculate_net_radial_force(self):
        centrifugal_force = 500
        radial_force = 1000
        wrap_angle = np.pi / 2
        expected_force = (centrifugal_force + radial_force) * 2 * np.sin(wrap_angle / 2)
        result = self.simulator_primary.calculate_net_radial_force(centrifugal_force, radial_force, wrap_angle)
        self.assertAlmostEqual(result, expected_force, places=5)

    def test_calculate_radial_force(self):
        ω = 100
        shift_distance = 0.1
        wrap_angle = np.pi / 2
        clamping_force = 1000
        centrifugal_force = self.simulator_primary.calculate_centrifugal_force(ω, shift_distance, wrap_angle)
        radial_force = self.simulator_primary.radial_force_from_clamping(clamping_force)
        expected_force = self.simulator_primary.calculate_net_radial_force(centrifugal_force, radial_force, wrap_angle)
        result = self.simulator_primary.calculate_radial_force(ω, shift_distance, wrap_angle, clamping_force)
        self.assertAlmostEqual(result, expected_force, places=5)

    def test_calculate_slack_tension(self):
        radial_force = 1000
        wrap_angle = np.pi / 2
        μ = 0.5
        θ = abs((wrap_angle - np.pi) / 2)
        denominator = np.cos(θ) * (1 + np.exp(μ * wrap_angle))
        expected_tension = radial_force / denominator
        result = self.simulator_primary.calculate_slack_tension(radial_force, wrap_angle, μ)
        self.assertAlmostEqual(result, expected_tension, places=5)

    def test_calculate_max_transferable_torque(self):
        tension = 1000
        μ = 0.5
        wrap_angle = np.pi / 2
        radius = 0.1
        expected_torque = tension * radius * (np.exp(μ * wrap_angle) - 1)
        result = self.simulator_primary.calculate_max_transferable_torque(tension, μ, wrap_angle, radius)
        self.assertAlmostEqual(result, expected_torque, places=5)

if __name__ == '__main__':
    unittest.main()