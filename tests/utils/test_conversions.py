import unittest
import math

from utils.conversions import (
    rpm_to_rad_s,
    rad_s_to_rpm,
    rad_to_deg,
    deg_to_rad,
    circumference,
    inch_to_meter
)


class TestConversions(unittest.TestCase):

    def test_rpm_to_rad_s(self):
        self.assertAlmostEqual(rpm_to_rad_s(60), 2 * math.pi)
        self.assertAlmostEqual(rpm_to_rad_s(0), 0)
        self.assertAlmostEqual(rpm_to_rad_s(120), 4 * math.pi)

    def test_rad_s_to_rpm(self):
        self.assertAlmostEqual(rad_s_to_rpm(2 * math.pi), 60)
        self.assertAlmostEqual(rad_s_to_rpm(0), 0)
        self.assertAlmostEqual(rad_s_to_rpm(4 * math.pi), 120)

    def test_rad_to_deg(self):
        self.assertAlmostEqual(rad_to_deg(math.pi), 180)
        self.assertAlmostEqual(rad_to_deg(0), 0)
        self.assertAlmostEqual(rad_to_deg(math.pi / 2), 90)

    def test_deg_to_rad(self):
        self.assertAlmostEqual(deg_to_rad(180), math.pi)
        self.assertAlmostEqual(deg_to_rad(0), 0)
        self.assertAlmostEqual(deg_to_rad(90), math.pi / 2)

    def test_circumference(self):
        self.assertAlmostEqual(circumference(1), 2 * math.pi)
        self.assertAlmostEqual(circumference(0), 0)
        self.assertAlmostEqual(circumference(2), 4 * math.pi)

    def test_inch_to_meter(self):
        self.assertAlmostEqual(inch_to_meter(1), 0.0254)
        self.assertAlmostEqual(inch_to_meter(0), 0)
        self.assertAlmostEqual(inch_to_meter(10), 0.254)


if __name__ == '__main__':
    unittest.main()