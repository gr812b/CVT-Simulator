from models.car_model import CarModel
from models.radial_model import RadialPulleyModel
from models.external_load_model import LoadModel
from models.engine_model import EngineModel
from models.primary_pulley_model import PrimaryPulleyModel
from models.secondary_pulley_model import SecondaryPulleyModel
from models.belt_model import BeltModel
from models.cvt_shift_model import CvtShiftModel
from constants.engine_specs import torque_curve
from constants.car_specs import ENGINE_INERTIA
from utils.conversions import deg_to_rad
from utils.argument_parser import SimulationArgs


def get_models(args: SimulationArgs):
    # Vehicle dynamics
    engine_model = EngineModel(torque_curve=torque_curve, inertia=ENGINE_INERTIA)
    load_model = LoadModel(
        car_mass=args.vehicle_weight + args.driver_weight,
        incline_angle=deg_to_rad(args.angle_of_incline),
    )
    car_model = CarModel(
        car_mass=args.vehicle_weight + args.driver_weight,
        load_model=load_model,
        engine_model=engine_model,
    )

    # CVT dynamics
    primary_model = PrimaryPulleyModel(
        spring_coeff_comp=args.primary_spring_rate,
        initial_compression=args.primary_spring_pretension,
        flyweight_mass=args.flyweight_mass,
        ramp_type=args.primary_ramp_geometry,
    )
    secondary_model = SecondaryPulleyModel(
        spring_coeff_tors=args.secondary_torsion_spring_rate,
        spring_coeff_comp=args.secondary_compression_spring_rate,
        initial_rotation=deg_to_rad(args.secondary_rotational_spring_pretension),
        initial_compression=args.secondary_linear_spring_pretension,
        ramp_type=args.secondary_helix_geometry,
    )
    primary_belt_model = BeltModel(primary=True)
    secondary_belt_model = BeltModel(primary=False)
    primary_radial_model = RadialPulleyModel(
        primary=True,
        pulley_model=primary_model,
        belt_model=primary_belt_model,
    )
    secondary_radial_model = RadialPulleyModel(
        primary=False,
        pulley_model=secondary_model,
        belt_model=secondary_belt_model,
    )
    cvt_shift = CvtShiftModel(
        engine_model,
        primary_radial_model,
        secondary_radial_model,
    )

    return car_model, cvt_shift
