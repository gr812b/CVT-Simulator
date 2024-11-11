import argparse


def get_arguments():
    parser = argparse.ArgumentParser(description="Simulate a Baja SAE car")
    parser.add_argument(
        "--incline_angle",
        type=float,
        default=0.0,
        help="Incline angle in degrees (default: 0.0)",
    )

    return parser.parse_args()
