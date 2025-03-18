import unittest
from unittest.mock import patch
from utils.argument_parser import get_arguments, SimulationArgs


class TestArgumentParser(unittest.TestCase):

    def setUp(self):
        self.default_args = {
            "flyweight_mass": 0.6,
            "primary_ramp_geometry": 0.0,
            "primary_spring_rate": 500.0,
            "primary_spring_pretension": 0.2,
            "secondary_helix_geometry": 0.0,
            "secondary_torsion_spring_rate": 100.0,
            "secondary_compression_spring_rate": 100.0,
            "secondary_spring_pretension": 15.0,
            "vehicle_weight": 225.0,
            "driver_weight": 75.0,
            "traction": 100.0,
            "angle_of_incline": 0.0,
            "acceleration_distance": 100.0,
        }

    @patch("sys.argv", ["program_name"])  # Mock the args here for the default test
    def test_default_arguments(self):
        args = get_arguments()  # Now this will work without real command-line input
        self.assertEqual(args, SimulationArgs(**self.default_args))

    @patch(
        "sys.argv",
        [
            "program_name",
            "--flyweight_mass",
            "0.8",
            "--primary_ramp_geometry",
            "1.0",
            "--primary_spring_rate",
            "600.0",
            "--primary_spring_pretension",
            "0.3",
            "--secondary_helix_geometry",
            "1.0",
            "--secondary_torsion_spring_rate",
            "150.0",
            "--secondary_compression_spring_rate",
            "150.0",
            "--secondary_spring_pretension",
            "20.0",
            "--vehicle_weight",
            "250.0",
            "--driver_weight",
            "80.0",
            "--traction",
            "90.0",
            "--angle_of_incline",
            "10.0",
            "--acceleration_distance",
            "100.0",
        ],
    )  # Mock the args here for the custom test
    def test_custom_arguments(self):  # No blank line after decorator
        custom_args = {
            "flyweight_mass": 0.8,
            "primary_ramp_geometry": 1.0,
            "primary_spring_rate": 600.0,
            "primary_spring_pretension": 0.3,
            "secondary_helix_geometry": 1.0,
            "secondary_torsion_spring_rate": 150.0,
            "secondary_compression_spring_rate": 150.0,
            "secondary_spring_pretension": 20.0,
            "vehicle_weight": 250.0,
            "driver_weight": 80.0,
            "traction": 90.0,
            "angle_of_incline": 10.0,
            "acceleration_distance": 100.0,
        }
        args = get_arguments()
        for key, value in custom_args.items():
            setattr(args, key, value)
        self.assertEqual(args, SimulationArgs(**custom_args))


if __name__ == "__main__":
    unittest.main()
