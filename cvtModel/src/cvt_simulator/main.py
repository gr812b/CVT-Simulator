from cvt_simulator.models.model_initializer import get_models
from cvt_simulator.simulation_runner import SimulationRunner
from cvt_simulator.utils.simulation_args import SimulationArgs
from cvt_simulator.utils.frontend_output import FormattedSimulationResult

def simulate_cvt_model(args: SimulationArgs, out_csv: str = "simulation_output.csv"):
  car_model, cvt_model = get_models(args)

  simulation_runner = SimulationRunner(car_model, cvt_model)
  result = simulation_runner.run_simulation()
  # Save outputs
  result.write_csv(out_csv)
  formatted = FormattedSimulationResult.from_csv(out_csv) # .write_formatted_csv()
  formatted.write_formatted_csv()

  return formatted

def main():
  simulate_cvt_model(SimulationArgs())

if __name__ == "__main__":
  main()
