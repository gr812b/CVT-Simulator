from cvt_simulator.models.car_model import CarModel
from cvt_simulator.models.external_load_model import LoadModel
from cvt_simulator.models.engine_model import EngineModel
from cvt_simulator.models.pulley.physical_primary_pulley import PhysicalPrimaryPulley
from cvt_simulator.models.pulley.physical_secondary_pulley import (
    PhysicalSecondaryPulley,
)
from cvt_simulator.models.cvt_shift_model import CvtShiftModel
from cvt_simulator.constants.engine_specs import safe_torque_curve
from cvt_simulator.utils.conversions import deg_to_rad
from cvt_simulator.utils.simulation_args import SimulationArgs
from cvt_simulator.models.slip_model import SlipModel
from cvt_simulator.models.engine_accel_model import EngineAccelModel
from cvt_simulator.models.system_model import SystemModel


def get_models(args: SimulationArgs):
    # Vehicle dynamics
    engine_model = EngineModel(torque_curve=safe_torque_curve)
    load_model = LoadModel(
        car_mass=args.vehicle_weight + args.driver_weight,
        incline_angle=deg_to_rad(args.angle_of_incline),
    )

    # CVT dynamics
    primary_pulley = PhysicalPrimaryPulley(
        spring_coeff_comp=args.primary_spring_rate,
        initial_compression=args.primary_spring_pretension,
        flyweight_mass=args.flyweight_mass,
        # TODO: Handle ramp_type conversion if needed
    )
    secondary_pulley = PhysicalSecondaryPulley(
        spring_coeff_tors=args.secondary_torsion_spring_rate,
        spring_coeff_comp=args.secondary_compression_spring_rate,
        initial_rotation=deg_to_rad(args.secondary_rotational_spring_pretension),
        initial_compression=args.secondary_linear_spring_pretension,
        # TODO: Handle ramp_type conversion if needed
    )

    cvt_shift = CvtShiftModel(
        engine_model=engine_model,
        primary_pulley=primary_pulley,
        secondary_pulley=secondary_pulley,
    )

    slip_model = SlipModel(
        load_model=load_model,
        engine_model=engine_model,
        car_mass=args.vehicle_weight + args.driver_weight,
        primary_pulley=primary_pulley,
        secondary_pulley=secondary_pulley,
    )

    car_model = CarModel(
        car_mass=args.vehicle_weight + args.driver_weight,
        load_model=load_model,
    )
    engine_accel_model = EngineAccelModel(engine_model=engine_model)

    system_model = SystemModel(
        slip_model=slip_model,
        engine_accel_model=engine_accel_model,
        car_model=car_model,
        cvt_shift_model=cvt_shift,
    )

    return system_model
