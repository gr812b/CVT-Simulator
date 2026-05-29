from typing import Callable, Optional
from cvt_simulator.sim.simulation_runner import SimulationRunner
from cvt_simulator.sim_utils.simulation_args import SimulationArgs
from cvt_simulator.utils.frontend_output import SimulationAnalysisResult


def simulate_cvt_model(
    args: SimulationArgs,
    out_csv: str = "simulation_output.csv",
    progress_callback: Optional[Callable[[float], None]] = None,
):
    simulation_runner = SimulationRunner.from_simulation_args(
        args,
        progress_callback=progress_callback,
    )
    result = simulation_runner.run_simulation()
    result.write_csv(out_csv)

    formatted = SimulationAnalysisResult(result, args)

    return formatted


def main():
    formatted = simulate_cvt_model(SimulationArgs())
    formatted.write_analysis_csv("front_end_output.csv")


if __name__ == "__main__":
    main()
