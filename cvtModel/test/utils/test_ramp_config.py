import unittest

from cvt_simulator.models.ramps.ramp_config import PiecewiseRampConfig


class TestRampConfigParsing(unittest.TestCase):
    def test_from_dict_coerces_string_quadrant(self):
        config = PiecewiseRampConfig.from_dict(
            {
                "segments": [
                    {"type": "linear", "length": "0.01", "angle": "25"},
                    {
                        "type": "circular",
                        "length": "0.02",
                        "angle_start": "30",
                        "angle_end": "20",
                        "quadrant": "2",
                    },
                ]
            }
        )

        circular = config.segments[1]
        self.assertEqual(circular.quadrant, 2)

    def test_from_dict_rejects_invalid_quadrant(self):
        with self.assertRaises(ValueError):
            PiecewiseRampConfig.from_dict(
                {
                    "segments": [
                        {
                            "type": "circular",
                            "length": 0.02,
                            "angle_start": 30,
                            "angle_end": 20,
                            "quadrant": "0",
                        }
                    ]
                }
            )


if __name__ == "__main__":
    unittest.main()
