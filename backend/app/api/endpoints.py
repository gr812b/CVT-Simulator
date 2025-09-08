from fastapi import APIRouter, Body

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
