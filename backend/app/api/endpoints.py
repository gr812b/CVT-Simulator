import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from cvt_simulator import (
    simulate_cvt_model,
    SimulationArgs,
    CarSpecs,
)
from cvt_simulator.models.ramps.ramp_preview import generate_ramp_preview
from ..models.response_models import (
    FormattedResultModel,
    SimulationArgsInput,
    PiecewiseRampConfigModel,
    RampPreviewResponse,
    StreamMessage,
)

router = APIRouter()


@router.get("/")
def ping():
    return "pong"


@router.get("/constants", response_model=CarSpecs)
def get_constants():
    """
    Get the physical constants and specifications used by the CVT simulator.
    These values are useful for visualization and understanding the simulation parameters.
    Calculated values like max_shift and center_to_center are automatically computed.
    """
    return CarSpecs()


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


@router.post("/run/stream", responses={200: {"model": StreamMessage}})
def run_stream(payload: SimulationArgsInput | None = None):  # type: ignore
    """
    Run CVT simulation with streaming progress updates.
    Returns newline-delimited JSON (NDJSON) stream with messages:
    - StreamProgressMessage: {"type": "progress", "percent": 12.5}
    - StreamCompleteMessage: {"type": "complete", "data": {...}}
    - StreamErrorMessage: {"type": "error", "message": "..."}
    """
    from queue import Queue, Empty
    import threading

    def generate():
        try:
            args = payload.model_dump(exclude_none=True) if payload else {}
            args = SimulationArgs.from_mapping(args)

            # Thread-safe queue for communication
            message_queue = Queue()

            def progress_callback(percent: float):
                # Called from simulation thread - put message in queue
                message_queue.put({"type": "progress", "percent": round(percent, 1)})

            def run_simulation_thread():
                try:
                    result = simulate_cvt_model(
                        args, progress_callback=progress_callback
                    )
                    message_queue.put({"type": "complete", "data": result})
                except Exception as e:
                    import traceback

                    message_queue.put(
                        {
                            "type": "error",
                            "message": str(e),
                            "traceback": traceback.format_exc(),
                        }
                    )

            # Start simulation in background thread
            # TODO: Add cancellation to cvtModel to drop unused requests
            sim_thread = threading.Thread(target=run_simulation_thread, daemon=True)
            sim_thread.start()

            # Stream messages as they arrive
            while True:
                try:
                    # Block for up to 0.5 seconds waiting for a message
                    message = message_queue.get(timeout=0.5)

                    if message["type"] == "complete":
                        result = message["data"]
                        # Convert to Pydantic model the same way /run does
                        pydantic_result = FormattedResultModel.model_validate(
                            result, from_attributes=True
                        )
                        yield json.dumps(
                            {
                                "type": "complete",
                                "data": pydantic_result.model_dump(),
                            }
                        ) + "\n"
                        break
                    elif message["type"] == "error":
                        yield json.dumps(
                            {"type": "error", "message": message["message"]}
                        ) + "\n"
                        break
                    else:
                        # Progress update - yield immediately with padding to force flush
                        msg = json.dumps(message) + "\n"
                        # Add padding to force proxies/CDN to flush the chunk
                        # Uncomment these lines when running on servers that buffer small responses
                        # Such as Github Codespaces
                        # padding = " " * (2048 - len(msg)) + "\n"
                        yield msg  # + padding

                except Empty:
                    # No message yet, check if thread is still alive
                    if not sim_thread.is_alive():
                        # Thread died without sending completion - something went wrong
                        yield json.dumps(
                            {
                                "type": "error",
                                "message": "Simulation thread terminated unexpectedly",
                            }
                        ) + "\n"
                        break
                    # Otherwise continue waiting for messages

        except Exception as e:
            import traceback

            yield json.dumps(
                {
                    "type": "error",
                    "message": str(e),
                    "traceback": traceback.format_exc(),
                }
            ) + "\n"

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# TODO: Remove this logic from endpoints / bake into cvtModel simulator
@router.post("/ramp/preview", response_model=RampPreviewResponse)
def preview_ramp(config: PiecewiseRampConfigModel):  # type: ignore
    """Generate preview data for a custom ramp configuration."""
    try:
        # Use the centralized ramp preview generator
        result = generate_ramp_preview(config.model_dump(), num_points=500)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid ramp configuration: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error generating ramp preview: {str(e)}"
        )
