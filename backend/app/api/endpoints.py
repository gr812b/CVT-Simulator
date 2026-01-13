from typing import List

import numpy as np
from fastapi import APIRouter, HTTPException

from cvt_simulator import (
    simulate_cvt_model,
    SimulationArgs,
    PiecewiseRampConfig,
    PiecewiseRamp,
)

from ..models.response_models import (
    FormattedResultModel,
    SimulationArgsInput,
    PiecewiseRampConfigModel,
    RampPreviewResponse,
)

router = APIRouter()


@router.get("/")
def ping():
    return "pong"


# Example curl commands to test the /run endpoint:
# Test with no parameters (empty payload):
# curl -X POST "http://127.0.0.1:8000/run" -H "accept: application/json" -H "Content-Type: application/json" -d "{}"
#
# Test with flyweight_mass parameter:
# curl -X POST "http://127.0.0.1:8000/run" -H "accept: application/json" -H "Content-Type: application/json" -d "{\"flyweight_mass\":0.4}"


@router.post("/run", response_model=FormattedResultModel)
def run(payload: SimulationArgsInput | None = None):  # type: ignore
    """Run CVT simulation with optional custom parameters."""
    args = payload.model_dump(exclude_none=True) if payload else {}
    args = SimulationArgs.from_mapping(args)
    result = simulate_cvt_model(args)
    return result


# TODO: Remove this logic from endpoints / bake into cvtModel simulator
@router.post("/ramp/preview", response_model=RampPreviewResponse)
def preview_ramp(config: PiecewiseRampConfigModel):
    """Generate preview data for a custom ramp configuration."""
    try:
        # Use factory method to properly handle type discrimination
        config_dataclass = PiecewiseRampConfig.from_dict(config.model_dump())
        ramp = PiecewiseRamp.from_config(config_dataclass)

        if not ramp.segments:
            raise HTTPException(
                status_code=400, detail="Ramp must have at least one segment"
            )

        x_min = ramp.segments[0].x_start
        x_max = ramp.segments[-1].x_end

        # Generate 100 sample points for smooth visualization
        x_points = np.linspace(x_min, x_max, 100)

        heights: List[float] = []
        slopes: List[float] = []

        for x in x_points:
            try:
                heights.append(float(ramp.height(x)))
                slopes.append(float(ramp.slope(x)))
            except ValueError as e:
                raise HTTPException(
                    status_code=400, detail=f"Error calculating ramp at x={x}: {e}"
                )

        return {
            "x": x_points.tolist(),
            "y": heights,
            "slopes": slopes,
            "x_min": float(x_min),
            "x_max": float(x_max),
        }
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid ramp configuration: {str(e)}"
        )
