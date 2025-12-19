# backend/models/response_models.py
from .auto_model import model_from_class, partial_model_from_class
from cvt_simulator import FormattedSimulationResult, SimulationArgs, PiecewiseRampConfig

# Auto-generate Pydantic models
SimulationArgsInput = partial_model_from_class(SimulationArgs)
FormattedResultModel = model_from_class(FormattedSimulationResult)
PiecewiseRampConfigModel = model_from_class(PiecewiseRampConfig)
