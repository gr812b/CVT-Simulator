import argparse
from dataclasses import dataclass


@dataclass
class SimulationArgs:
    flyweight_mass: float
    primary_ramp_geometry: float
    primary_spring_rate: float
    primary_spring_pretension: float
    secondary_helix_geometry: float
    secondary_torsion_spring_rate: float
    secondary_compression_spring_rate: float
    secondary_rotational_spring_pretension: float
    secondary_linear_spring_pretension: float
    vehicle_weight: float
    driver_weight: float
    traction: float
    angle_of_incline: float
    total_distance: float


def get_arguments() -> SimulationArgs:
    parser = argparse.ArgumentParser(description="Simulate a Baja SAE car")
    parser.add_argument(
        "--flyweight_mass",
        type=float,
        default=0.8,
        help="Weight of the primary pulley in kilograms (default: 0.6 kg)",
    )
    parser.add_argument(
        "--primary_ramp_geometry",
        type=float,
        default=1,
        help="Ramp geometry of the primary pulley (default: ???)",
    )
    parser.add_argument(
        "--primary_spring_rate",
        type=float,
        default=1000,
        help="Spring rate of the primary pulley in N/m (default: 500.0 N/m)",
    )
    parser.add_argument(
        "--primary_spring_pretension",
        type=float,
        default=0,
        help="Spring pretension of the primary pulley in m (default: 0.2 m)",
    )
    parser.add_argument(
        "--secondary_helix_geometry",
        type=float,
        default=1,
        help="Helix geometry of the secondary pulley (default: 0.0)",
    )
    parser.add_argument(
        "--secondary_torsion_spring_rate",
        type=float,
        default=30,
        help="Spring rate of the secondary pulley in N/m (default: 100.0 Nm/rad)",
    )
    parser.add_argument(
        "--secondary_compression_spring_rate",
        type=float,
        default=1,
        help="Spring rate of the secondary pulley in N/m (default: 100.0 N/m)",
    )
    parser.add_argument(
        "--secondary_rotational_spring_pretension",
        type=float,
        default=45,
        help="Spring pretension of the secondary pulley in degrees (default: 45 degrees)",
    ),
    parser.add_argument(
        "--secondary_linear_spring_pretension",
        type=float,
        default=0.1,
        help="Spring pretension of the secondary pulley in degrees (default: 45 degrees)",
    )
    parser.add_argument(
        "--vehicle_weight",
        type=float,
        default=225.0,
        help="Weight of the vehicle in kilograms (default: 225.0 kg)",
    )
    parser.add_argument(
        "--driver_weight",
        type=float,
        default=75.0,
        help="Weight of the driver in kilograms (default: 75.0 kg)",
    )
    parser.add_argument(
        "--traction",
        type=float,
        default=100.0,
        help="Traction force in percentage (default: 100.0 %)",
    )
    parser.add_argument(
        "--angle_of_incline",
        type=float,
        default=0.0,
        help="Angle of incline in degrees (default: 0.0 degrees)",
    )
    parser.add_argument(
        "--total_distance",
        type=float,
        default=200.0,
        help="Total distance in meters (default: 100.0 m)",
    )

    args = parser.parse_args()
    return SimulationArgs(**vars(args))
