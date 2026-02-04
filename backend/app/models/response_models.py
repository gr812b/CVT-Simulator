# backend/models/response_models.py
from typing import List, Union, Literal
from pydantic import BaseModel
from .auto_model import model_from_class, partial_model_from_class
from cvt_simulator import (
    FormattedSimulationResult,
    SimulationArgs,
    PiecewiseRampConfig,
    AllSolverResults,
)

# Auto-generate Pydantic models
SimulationArgsInput = partial_model_from_class(SimulationArgs)
FormattedResultModel = model_from_class(FormattedSimulationResult)
PiecewiseRampConfigModel = model_from_class(PiecewiseRampConfig)
AllSolverResultsModel = model_from_class(AllSolverResults)


# TODO: Bake this into the auto_model system
class RampPreviewResponse(BaseModel):
    x: List[float]
    y: List[float]
    slopes: List[float]
    x_min: float
    x_max: float


# Streaming response models
class StreamProgressMessage(BaseModel):
    type: Literal["progress"]
    percent: float


class StreamCompleteMessage(BaseModel):
    type: Literal["complete"]
    data: FormattedResultModel  # type: ignore


# TODO: Don't expose traceback in production
class StreamErrorMessage(BaseModel):
    type: Literal["error"]
    message: str
    traceback: str | None = None


StreamMessage = Union[StreamProgressMessage, StreamCompleteMessage, StreamErrorMessage]
