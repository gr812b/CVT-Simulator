# File purpose is to determine shift starting point

from simulations.cvt_shift import CvtShift
from simulations.load_simulation import LoadSimulator
from simulations.engine_simulation import EngineSimulator
from simulations.primary_pulley import PrimaryPulley
from simulations.secondary_pulley import SecondaryPulley
from simulations.belt_simulator import BeltSimulator
from constants.engine_specs import torque_curve
from constants.car_specs import (
    ENGINE_INERTIA,
)
from utils.conversions import rpm_to_rad_s, deg_to_rad
from utils.argument_parser import get_arguments
from utils.theoretical_models import TheoreticalModels as tm

args = get_arguments()

engine_simulator = EngineSimulator(torque_curve=torque_curve, inertia=ENGINE_INERTIA)
load_simulator = LoadSimulator(
    car_mass=args.vehicle_weight + args.driver_weight,
    incline_angle=deg_to_rad(args.angle_of_incline),
)
primary_simulator = PrimaryPulley(
    spring_coeff_comp=args.primary_spring_rate,
    initial_compression=args.primary_spring_pretension,
    flyweight_mass=args.flyweight_mass,
    ramp_type=args.primary_ramp_geometry
)
secondary_simulator = SecondaryPulley(
    spring_coeff_tors=args.secondary_torsion_spring_rate,
    spring_coeff_comp=args.secondary_compression_spring_rate,
    initial_rotation=deg_to_rad(args.secondary_spring_pretension),
    initial_compression=1.5,  # TODO: Use constants
    ramp_type=args.secondary_helix_geometry
)
primary_belt = BeltSimulator(primary=True)
secondary_belt = BeltSimulator(primary=False)
cvt_shift = CvtShift(
    engine_simulator,
    primary_simulator,
    secondary_simulator,
    primary_belt,
    secondary_belt,
)


engine_velocity = rpm_to_rad_s(2000)
shift = 0

engine_torque = engine_simulator.get_torque(engine_velocity)

# Calculate forces using the provided simulators
primary_force = primary_simulator.calculate_net_force(shift, engine_velocity)
secondary_force = secondary_simulator.calculate_net_force(
    engine_torque * tm.current_cvt_ratio(shift), shift
)

# Calculate wrap angles and convert to radial forces
primary_wrap_angle = tm.primary_wrap_angle(shift)
secondary_wrap_angle = tm.secondary_wrap_angle(shift)
primary_radial = primary_belt.calculate_radial_force(
    engine_velocity, shift, primary_wrap_angle, primary_force
)
secondary_radial = secondary_belt.calculate_radial_force(
    engine_velocity, shift, secondary_wrap_angle, secondary_force
)

print(
    f"Primary belt radial force: {primary_radial:.2f}, Secondary belt radial force: {secondary_radial:.2f}"
)
