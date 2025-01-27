import argparse


def get_arguments():
    parser = argparse.ArgumentParser(description="Simulate a Baja SAE car")
    parser.add_argument(
        "--primary_weight",
        type=float,
        default=0.0,
        help="Weight of the primary pulley in kilograms (default: 0.0 kg)",
    )
    parser.add_argument(
        "--primary_ramp_geometry",
        type=float,
        default=0.0,
        help="Ramp geometry of the primary pulley (default: 0.0)",
    )
    parser.add_argument(
        "--primary_spring_rate",
        type=float,
        default=0.0,
        help="Spring rate of the primary pulley in N/m (default: 0.0 N/m)",
    )
    parser.add_argument(
        "--primary_spring_pretension",
        type=float,
        default=0.0,
        help="Spring pretension of the primary pulley in N (default: 0.0 N)",
    )
    parser.add_argument(
        "--secondary_helix_geometry",
        type=float,
        default=0.0,
        help="Helix geometry of the secondary pulley (default: 0.0)",
    )
    parser.add_argument(
        "--secondary_spring_rate",
        type=float,
        default=0.0,
        help="Spring rate of the secondary pulley in N/m (default: 0.0 N/m)",
    )
    parser.add_argument(
        "--secondary_spring_pretension",
        type=float,
        default=0.0,
        help="Spring pretension of the secondary pulley in N (default: 0.0 N)",
    )
    parser.add_argument(
        "--vehicle_weight",
        type=float,
        default=0.0,
        help="Weight of the vehicle in kilograms (default: 0.0 kg)",
    )
    parser.add_argument(
        "driver_weight",
        type=float,
        default=0.0,
        help="Weight of the driver in kilograms (default: 0.0 kg)",
    )
    parser.add_argument(
        "traction",
        type=float,
        default=0.0,
        help="Traction force in N (default: 0.0 N)",
    )
    parser.add_argument(
        "angle_of_incline",
        type=float,
        default=0.0,
        help="Angle of incline in degrees (default: 0.0 degrees)",
    )

    return parser.parse_args()
