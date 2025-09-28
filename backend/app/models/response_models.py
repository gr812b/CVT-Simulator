# backend/models/response_models.py
from .auto_model import model_from_class
from cvt_simulator import FormattedSimulationResult

FormattedResultModel = model_from_class(FormattedSimulationResult)
