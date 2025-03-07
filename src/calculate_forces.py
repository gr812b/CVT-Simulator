from matplotlib import pyplot as plt
import numpy as np
from scipy.integrate import solve_ivp
from simulations.car_simulation import CarSimulator
from simulations.load_simulation import LoadSimulator
from utils.system_state import SystemState
from utils.simulation_result import SimulationResult
from simulations.engine_simulation import EngineSimulator
from simulations.primary_pulley import PrimaryPulley
from simulations.secondary_pulley import SecondaryPulley
from simulations.belt_simulator import BeltSimulator
from constants.engine_specs import torque_curve
from constants.car_specs import (
    ENGINE_INERTIA,
    GEARBOX_RATIO,
    FRONTAL_AREA,
    DRAG_COEFFICIENT,
    CAR_MASS,
    WHEEL_RADIUS,
    INITIAL_FLYWEIGHT_RADIUS,
    HELIX_RADIUS,
    MAX_SHIFT,
)
from utils.conversions import rpm_to_rad_s, deg_to_rad
from utils.argument_parser import get_arguments
from utils.theoretical_models import TheoreticalModels as tm
from utils.simulation_constraints import constraints, logistic_clamp
import sys

args = get_arguments()

engine_simulator = EngineSimulator(torque_curve=torque_curve, inertia=ENGINE_INERTIA)
load_simulator = LoadSimulator(
    frontal_area=FRONTAL_AREA,
    drag_coefficient=DRAG_COEFFICIENT,
    car_mass=CAR_MASS + args.driver_weight,
    wheel_radius=WHEEL_RADIUS,
    gearbox_ratio=GEARBOX_RATIO,
    incline_angle=deg_to_rad(30),
)
car_simulator = CarSimulator(car_mass=CAR_MASS + args.driver_weight)
primary_simulator = PrimaryPulley(
    spring_coeff_comp=args.primary_spring_rate,
    initial_compression=args.primary_spring_pretension,
    flyweight_mass=args.flyweight_mass,
    initial_flyweight_radius=INITIAL_FLYWEIGHT_RADIUS,
)
secondary_simulator = SecondaryPulley(
    spring_coeff_tors=args.secondary_torsion_spring_rate,
    spring_coeff_comp=args.secondary_compression_spring_rate,
    initial_rotation=deg_to_rad(args.secondary_spring_pretension),
    initial_compression=0.1,  # TODO: Use constants
    helix_radius=HELIX_RADIUS,
)
primary_belt = BeltSimulator(
    μ_static=1.2,  # TODO: Use constants
    μ_kinetic=0.9,  # TODO: Use constants
    primary=True,
)
secondary_belt = BeltSimulator(
    μ_static=1.2,  # TODO: Use constants
    μ_kinetic=0.9,  # TODO: Use constants
    primary=False,
)


engine_velocity = rpm_to_rad_s(3400)
shift = 0

engine_torque = engine_simulator.get_torque(engine_velocity)

primary_force = primary_simulator.calculate_net_force(
    shift,
    engine_velocity,
)
secondary_force = secondary_simulator.calculate_net_force(
    engine_torque * tm.current_cvt_ratio(shift),
    shift,
)
primary_wrap_angle = tm.primary_wrap_angle(shift)
secondary_wrap_angle = tm.secondary_wrap_angle(shift)

primary_belt_radial = primary_belt.calculate_radial_force(
    engine_velocity,
    shift,
    primary_wrap_angle,
    primary_force,
)
secondary_belt_radial = secondary_belt.calculate_radial_force(
    engine_velocity,
    shift,
    secondary_wrap_angle,
    secondary_force,
)

print(f"Primary belt radial force: {primary_belt_radial:.2f}, Secondary belt radial force: {secondary_belt_radial:.2f}")