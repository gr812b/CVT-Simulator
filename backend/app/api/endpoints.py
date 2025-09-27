from fastapi import APIRouter, Body
from cvt_simulator import simulate_cvt_model, SimulationArgs

router = APIRouter()


# Example curl command to test the endpoint:
# curl -X POST "http://127.0.0.1:8000/compute" \
#   -H "accept: application/json" \
#   -H "Content-Type: application/json" \
#   -d "{\"field\":\"test input\"}"


@router.post("/compute")
def compute(field: str = Body(..., embed=True)):
    result = f"Received: {field}"
    return {"result": result}


@router.get("/")
def ping():
    return "pong"

# Example curl commands to test the /run endpoint:
# Test with no parameters (empty payload):
# curl -X POST "http://127.0.0.1:8000/run" -H "accept: application/json" -H "Content-Type: application/json" -d "{}"
#
# Test with flyweight_mass parameter:
# curl -X POST "http://127.0.0.1:8000/run" -H "accept: application/json" -H "Content-Type: application/json" -d "{\"flyweight_mass\":0.4}"

@router.post("/run")
def run(payload: dict):
    # Partial JSON is fine; defaults fill the rest
    args = SimulationArgs.from_mapping(payload)
    print(payload)
    csv_path = simulate_cvt_model(args, out_csv="simulation_output.csv")
    return {"csv_path": csv_path}