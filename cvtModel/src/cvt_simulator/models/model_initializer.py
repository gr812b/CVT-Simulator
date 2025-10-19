from cvt_simulator.models.car_model import CarModel
from cvt_simulator.models.radial_model import RadialPulleyModel
from cvt_simulator.models.external_load_model import LoadModel
from cvt_simulator.models.engine_model import EngineModel
from cvt_simulator.models.primary_pulley_model import PrimaryPulleyModel
from cvt_simulator.models.secondary_pulley_model import SecondaryPulleyModel
from cvt_simulator.models.belt_model import BeltModel
from cvt_simulator.models.cvt_shift_model import CvtShiftModel
from cvt_simulator.constants.engine_specs import torque_curve
from cvt_simulator.constants.car_specs import ENGINE_INERTIA
from cvt_simulator.utils.conversions import deg_to_rad
from cvt_simulator.utils.simulation_args import SimulationArgs
from cvt_simulator.models.engine_slip_model import slip_model


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

    # TODO: TEMP Engine slip model
    engine_slip_model = slip_model(
        load_model=load_model,
        engine_model=engine_model,
    )

    return car_model, cvt_shift, engine_slip_model
