from simulation_runner import SimulationRunner
from models.external_load_model import LoadModel
from utils.simulation_result import SimulationResult
from models.engine_model import EngineModel
from models.primary_pulley_model import PrimaryPulleyModel
from models.secondary_pulley_model import SecondaryPulleyModel
from models.belt_model import BeltModel
from models.cvt_shift_model import CvtShiftModel
from constants.engine_specs import torque_curve
from constants.car_specs import ( ENGINE_INERTIA )
from utils.conversions import deg_to_rad
from utils.argument_parser import get_arguments
from utils.frontend_output import FormattedSimulationResult


# Parse arguments
args = get_arguments()

# Initialize models with args
engine_model = EngineModel(torque_curve=torque_curve, inertia=ENGINE_INERTIA)
load_model = LoadModel(
    car_mass=args.vehicle_weight + args.driver_weight,
    incline_angle=deg_to_rad(args.angle_of_incline),
)
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
cvt_shift = CvtShiftModel(
    engine_model,
    primary_model,
    secondary_model,
    primary_belt_model,
    secondary_belt_model,
)

# Run multi-phase simulation
simulationRunner = SimulationRunner(
    engine_model,
    load_model,
    cvt_shift,
)
result = simulationRunner.run_simulation()

# Handle output
result.write_csv("simulation_output.csv")
FormattedSimulationResult.from_csv().write_formatted_csv()
