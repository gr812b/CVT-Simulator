from models.model_initializer import get_models
from simulation_runner import SimulationRunner
from utils.argument_parser import get_arguments
from utils.frontend_output import FormattedSimulationResult


# Parse arguments 
args = get_arguments()

# Initialize models with args
car_model, cvt_model = get_models(args)

# Run multi-phase simulation
simulationRunner = SimulationRunner(
    car_model,
    cvt_model,
)
result = simulationRunner.run_simulation()

# Handle output
result.write_csv("simulation_output.csv")
FormattedSimulationResult.from_csv().write_formatted_csv()
