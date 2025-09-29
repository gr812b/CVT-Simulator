from fastapi import APIRouter
from ..models.response_models import FormattedResultModel, SimulationArgsInput
from cvt_simulator import simulate_cvt_model, SimulationArgs

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
    args = payload.model_dump(exclude_none=True) if payload else {}
    args = SimulationArgs.from_mapping(args)
    result = simulate_cvt_model(args)

    return result
