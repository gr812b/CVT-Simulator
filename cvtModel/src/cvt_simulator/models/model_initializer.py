from cvt_simulator.models.secondary_pulley_model import SecondaryPulleyModel
from cvt_simulator.models.external_load_model import LoadModel
from cvt_simulator.models.engine_model import EngineModel
from cvt_simulator.models.pulley.primary_pulley_flyweight import PhysicalPrimaryPulley
from cvt_simulator.models.pulley.secondary_pulley_torque_reactive import (
    PhysicalSecondaryPulley,
)
from cvt_simulator.models.cvt_shift_model import CvtShiftModel
from cvt_simulator.constants.engine_specs import safe_torque_curve
from cvt_simulator.utils.conversions import deg_to_rad
from cvt_simulator.utils.simulation_args import SimulationArgs
from cvt_simulator.models.slip_model import SlipModel
from cvt_simulator.models.belt_model import BeltModel
from cvt_simulator.models.primary_pulley_model import PrimaryPulleyModel
from cvt_simulator.models.system_model import SystemModel
from cvt_simulator.models.ramps.piecewise_ramp import PiecewiseRamp
from cvt_simulator.models.ramps.theta_ramp import ThetaRamp
from cvt_simulator.constants.car_specs import HELIX_RADIUS


def get_models(args: SimulationArgs):
    # Vehicle dynamics
    engine_model = EngineModel(torque_curve=safe_torque_curve)
    load_model = LoadModel(
        car_mass=args.vehicle_weight + args.driver_weight,
        incline_angle=deg_to_rad(args.angle_of_incline),
    )

    # CVT dynamics - convert ramp configs to ramp instances
    primary_pulley = PhysicalPrimaryPulley(
        spring_coeff_comp=args.primary_spring_rate,
        initial_compression=args.primary_spring_pretension,
        flyweight_mass=args.flyweight_mass,
        ramp=PiecewiseRamp.from_config(args.primary_ramp_config),
    )
    secondary_pulley = PhysicalSecondaryPulley(
        spring_coeff_tors=args.secondary_torsion_spring_rate,
        spring_coeff_comp=args.secondary_compression_spring_rate,
        initial_rotation=deg_to_rad(args.secondary_rotational_spring_pretension),
        initial_compression=args.secondary_linear_spring_pretension,
        ramp=ThetaRamp(
            PiecewiseRamp.from_config(args.secondary_ramp_config),
            HELIX_RADIUS,
        ),
    )

    cvt_shift = CvtShiftModel(
        engine_model=engine_model,
        primary_pulley=primary_pulley,
        secondary_pulley=secondary_pulley,
    )

    secondary_pulley_model = SecondaryPulleyModel(
        car_mass=args.vehicle_weight + args.driver_weight,
        load_model=load_model,
    )
    primary_pulley_model = PrimaryPulleyModel(engine_model=engine_model)

    belt_model = BeltModel()

    slip_model = SlipModel(
        load_model=load_model,
        engine_model=engine_model,
        car_mass=args.vehicle_weight + args.driver_weight,
        primary_pulley=primary_pulley,
        secondary_pulley=secondary_pulley,
        primary_pulley_model=primary_pulley_model,
        secondary_pulley_model=secondary_pulley_model,
        belt_model=belt_model,
    )

    system_model = SystemModel(
        slip_model=slip_model,
        belt_model=belt_model,
        primary_pulley_model=primary_pulley_model,
        secondary_pulley_model=secondary_pulley_model,
        cvt_shift_model=cvt_shift,
    )

    return system_model
