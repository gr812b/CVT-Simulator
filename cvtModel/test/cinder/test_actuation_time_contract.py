from __future__ import annotations

import unittest

from cinder.model.cvt.actuation import PulleyActuationContext
from cinder.studies.actuation import ActuationOperatingPoint


class ActuationTimeContractTest(unittest.TestCase):
    def test_pulley_context_requires_time(self) -> None:
        with self.assertRaises(TypeError):
            PulleyActuationContext(
                axial_position=0.0,
                axial_speed=0.0,
                shaft_speed=0.0,
            )

    def test_pulley_context_validates_time(self) -> None:
        with self.assertRaises(ValueError):
            PulleyActuationContext(
                time=float("nan"),
                axial_position=0.0,
                axial_speed=0.0,
                shaft_speed=0.0,
            )

    def test_static_study_point_requires_time(self) -> None:
        with self.assertRaises(TypeError):
            ActuationOperatingPoint(shift_position=0.0)

    def test_explicit_time_is_retained(self) -> None:
        context = PulleyActuationContext(
            time=2.75,
            axial_position=0.0,
            axial_speed=0.0,
            shaft_speed=0.0,
        )
        point = ActuationOperatingPoint(time=2.75, shift_position=0.0)
        self.assertEqual(context.time, 2.75)
        self.assertEqual(point.time, 2.75)


if __name__ == "__main__":
    unittest.main()
