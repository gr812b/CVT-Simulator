import unittest

from cvt_simulator.utils.theoretical_models import TheoreticalModels


class TestTheoreticalModels(unittest.TestCase):

    def test_hookes_law_comp(self):
        self.assertAlmostEqual(TheoreticalModels.hookes_law_comp(10, 2), 20)

    def test_hookes_law_tors(self):
        self.assertAlmostEqual(TheoreticalModels.hookes_law_tors(5, 3), 15)

    def test_centrifugal_force(self):
        self.assertAlmostEqual(TheoreticalModels.centrifugal_force(2, 3, 4), 72)

    def test_air_resistance(self):
        self.assertAlmostEqual(TheoreticalModels.air_resistance(1.2, 10, 2, 0.5), 60)

    def test_torque(self):
        self.assertAlmostEqual(TheoreticalModels.torque(100, 10), 10)

    def test_gearing(self):
        self.assertAlmostEqual(TheoreticalModels.gearing(2, 3), 6)

    def test_static_friction(self):
        self.assertAlmostEqual(TheoreticalModels.static_friction(0.5, 20), 10)

    def test_capstan_equation(self):
        self.assertAlmostEqual(
            TheoreticalModels.capstan_equation(100, 2, 0.3), 182.2118800390509
        )

    def test_newtons_second_law(self):
        self.assertAlmostEqual(TheoreticalModels.newtons_second_law(10, 9.8), 98)

    def test_primary_outer_radius(self):
        self.assertAlmostEqual(
            TheoreticalModels.primary_outer_radius(0), 0.036207699999999995
        )

    def test_secondary_outer_radius(self):
        self.assertAlmostEqual(
            TheoreticalModels.secondary_outer_radius(0), 0.10414225374493848
        )

    def test_current_effective_cvt_ratio(self):
        self.assertAlmostEqual(
            TheoreticalModels.current_effective_cvt_ratio(0), 3.39015972307032
        )

    def test_wrap_angle(self):
        self.assertAlmostEqual(
            TheoreticalModels.wrap_angle(0.026835099999999997, 0.09381489999999991),
            0.26693579785740573,
        )

    def test_primary_wrap_angle(self):
        self.assertAlmostEqual(
            TheoreticalModels.primary_wrap_angle(0),
            2.8708286084159145,
        )

    def test_secondary_wrap_angle(self):
        self.assertAlmostEqual(
            TheoreticalModels.secondary_wrap_angle(0),
            3.4123566987636718,
        )


if __name__ == "__main__":
    unittest.main()
