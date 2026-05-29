import unittest

import math

from cvt_simulator.constants.constants import GRAVITY, AIR_DENSITY


class LoadSimulator:
    def __init__(
        self,
        car_mass,
        drag_coefficient,
        frontal_area,
        wheel_radius,
        gearbox_ratio,
        incline_angle,
    ):
        self.car_mass = car_mass
        self.drag_coefficient = drag_coefficient
        self.frontal_area = frontal_area
        self.wheel_radius = wheel_radius
        self.gearbox_ratio = gearbox_ratio
        self.incline_angle = incline_angle
        self.g = GRAVITY
        self.air_density = AIR_DENSITY

    def calculate_incline_force(self):
        return self.car_mass * self.g * math.sin(self.incline_angle)

    def calculate_drag_force(self, velocity):
        return (
            0.5
            * self.air_density
            * velocity**2
            * self.frontal_area
            * self.drag_coefficient
        )

    def calculate_total_load_force(self, velocity):
        return self.calculate_incline_force() + self.calculate_drag_force(velocity)

    def calculate_gearbox_load(self, velocity):
        total = self.calculate_total_load_force(velocity)
        return total * self.wheel_radius / self.gearbox_ratio

    def calculate_acceleration(self, velocity, power):
        engine = power / (velocity * self.car_mass)
        air_resistance = self.calculate_drag_force(velocity) / self.car_mass
        gravity = self.g * math.sin(self.incline_angle)
        return engine - air_resistance - gravity


class TestLoadSimulator(unittest.TestCase):

    def setUp(self):
        self.car_mass = 1500  # kg
        self.drag_coefficient = 0.3  # unitless
        self.frontal_area = 2.2  # m^2
        self.wheel_radius = 0.3  # m
        self.gearbox_ratio = 4.0  # unitless
        self.incline_angle = 0.1  # radians
        self.simulator = LoadSimulator(
            self.car_mass,
            self.drag_coefficient,
            self.frontal_area,
            self.wheel_radius,
            self.gearbox_ratio,
            self.incline_angle,
        )

    def test_initialization(self):
        self.assertEqual(self.simulator.car_mass, self.car_mass)
        self.assertEqual(self.simulator.drag_coefficient, self.drag_coefficient)
        self.assertEqual(self.simulator.frontal_area, self.frontal_area)
        self.assertEqual(self.simulator.wheel_radius, self.wheel_radius)
        self.assertEqual(self.simulator.gearbox_ratio, self.gearbox_ratio)
        self.assertEqual(self.simulator.incline_angle, self.incline_angle)
        self.assertEqual(self.simulator.g, GRAVITY)
        self.assertEqual(self.simulator.air_density, AIR_DENSITY)

    def test_calculate_incline_force(self):
        expected_force = self.car_mass * GRAVITY * math.sin(self.incline_angle)
        self.assertAlmostEqual(self.simulator.calculate_incline_force(), expected_force)

    def test_calculate_drag_force(self):
        velocity = 30  # m/s
        expected_drag_force = (
            0.5 * AIR_DENSITY * velocity**2 * self.frontal_area * self.drag_coefficient
        )
        self.assertAlmostEqual(
            self.simulator.calculate_drag_force(velocity), expected_drag_force
        )

    def test_calculate_total_load_force(self):
        velocity = 30  # m/s
        incline_force = self.simulator.calculate_incline_force()
        drag_force = self.simulator.calculate_drag_force(velocity)
        expected_total_load_force = incline_force + drag_force
        self.assertAlmostEqual(
            self.simulator.calculate_total_load_force(velocity),
            expected_total_load_force,
        )

    def test_calculate_gearbox_load(self):
        velocity = 30  # m/s
        total_load_force = self.simulator.calculate_total_load_force(velocity)
        expected_gearbox_load = (
            total_load_force * self.wheel_radius / self.gearbox_ratio
        )
        self.assertAlmostEqual(
            self.simulator.calculate_gearbox_load(velocity), expected_gearbox_load
        )

    def test_calculate_acceleration(self):
        velocity = 30  # m/s
        power = 100000  # W
        engine = power / (velocity * self.car_mass)
        air_resistance = self.simulator.calculate_drag_force(velocity) / self.car_mass
        gravity = GRAVITY * math.sin(self.incline_angle)
        expected_acceleration = engine - air_resistance - gravity
        self.assertAlmostEqual(
            self.simulator.calculate_acceleration(velocity, power),
            expected_acceleration,
        )


if __name__ == "__main__":
    unittest.main()
