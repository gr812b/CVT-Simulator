import json
import multiprocessing
import time
from queue import Empty

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from cvt_simulator import (
    simulate_cvt_model,
    SimulationArgs,
    CarSpecs,
    solve_all,
)
from cvt_simulator.ramps.ramp_preview import generate_ramp_preview
from ..models.response_models import (
    FormattedResultModel,
    SimulationArgsInput,
    PiecewiseRampConfigModel,
    RampPreviewResponse,
    StreamMessage,
    AllSolverResultsModel,
)

router = APIRouter()

# Maximum wall-clock time allowed for a single streaming simulation request.
# If a solver gets stuck and exceeds this, the subprocess is hard-killed.
STREAM_TIMEOUT_SECONDS = 10 * 60  # 8 minutes


def _simulation_worker(args: SimulationArgs, result_queue) -> None:  # type: ignore
    """
    Module-level worker that runs simulate_cvt_model in a subprocess.

    Must be at module level for Windows (spawn-based multiprocessing) pickle
    compatibility. Running in a separate *process* (not thread) lets the parent
    hard-kill it via process.kill() when a solver gets stuck indefinitely,
    which is impossible with threads.

    The result is serialized to a plain dict before being queued to avoid any
    pickle issues with complex nested objects crossing the process boundary.
    """
    try:

        def progress_callback(percent: float):
            try:
                result_queue.put_nowait(
                    {"type": "progress", "percent": round(percent, 1)}
                )
            except Exception:
                pass  # Never let a failed progress update abort the simulation

        result = simulate_cvt_model(args, progress_callback=progress_callback)

        # Serialize inside the worker so we only pass a plain dict across the
        # process boundary – avoids pickling deeply-nested dataclass graphs.
        result_dict = FormattedResultModel.model_validate(
            result, from_attributes=True
        ).model_dump()
        result_queue.put({"type": "complete", "data": result_dict})

    except Exception as e:
        import traceback

        result_queue.put(
            {"type": "error", "message": str(e), "traceback": traceback.format_exc()}
        )


@router.get("/")
def ping():
    return "pong"


@router.get("/constants", response_model=CarSpecs)
def get_constants():
    """
    Get the physical constants and specifications used by the CVT simulator.
    These values are useful for visualization and understanding the simulation parameters.
    Calculated values like max_shift, center_to_center, and min/max effective CVT ratio are automatically computed.
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
    try:
        args = payload.model_dump(exclude_none=True) if payload else {}
        args = SimulationArgs.from_mapping(args)
        result = simulate_cvt_model(args)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid simulation input: {e}")


@router.post("/run/stream", responses={200: {"model": StreamMessage}})
def run_stream(payload: SimulationArgsInput | None = None):  # type: ignore
    """
    Run CVT simulation with streaming progress updates.
    Returns newline-delimited JSON (NDJSON) stream with messages:
    - StreamProgressMessage: {"type": "progress", "percent": 12.5}
    - StreamCompleteMessage: {"type": "complete", "data": {...}}
    - StreamErrorMessage: {"type": "error", "message": "..."}

    The simulation runs in a subprocess so that it can be hard-killed via
    process.kill() if the total elapsed wall-clock time exceeds
    STREAM_TIMEOUT_SECONDS (default 5 minutes). This is necessary because
    some solver paths can get stuck indefinitely inside C extensions that
    ignore Python thread interrupts.
    """

    def generate():
        proc = None
        try:
            args = payload.model_dump(exclude_none=True) if payload else {}
            args = SimulationArgs.from_mapping(args)

            # Spawn a fresh process so we can hard-kill it on timeout.
            # 'spawn' is used explicitly for cross-platform safety (avoids
            # fork+async deadlock issues on Linux and is the default on Windows).
            ctx = multiprocessing.get_context("spawn")
            result_queue = ctx.Queue()
            proc = ctx.Process(
                target=_simulation_worker,
                args=(args, result_queue),
                daemon=True,
            )
            proc.start()

            start_time = time.monotonic()

            # Stream messages as they arrive
            while True:
                elapsed = time.monotonic() - start_time
                remaining = STREAM_TIMEOUT_SECONDS - elapsed

                if remaining <= 0:
                    # Hard-kill the subprocess – this is safe even for stuck
                    # C-extension solvers because the OS terminates the process.
                    proc.kill()
                    proc.join(timeout=5)
                    yield json.dumps(
                        {
                            "type": "error",
                            "message": f"Simulation timed out after {STREAM_TIMEOUT_SECONDS}s",
                        }
                    ) + "\n"
                    return

                try:
                    # Cap the wait so the timeout check above runs regularly.
                    message = result_queue.get(timeout=min(0.5, remaining))

                    if message["type"] == "complete":
                        # Result was already serialized to a dict by the worker.
                        pydantic_result = FormattedResultModel.model_validate(
                            message["data"]
                        )
                        yield json.dumps(
                            {
                                "type": "complete",
                                "data": pydantic_result.model_dump(),
                            }
                        ) + "\n"
                        return
                    elif message["type"] == "error":
                        yield json.dumps(
                            {
                                "type": "error",
                                "message": message["message"],
                                "traceback": message.get("traceback"),
                            }
                        ) + "\n"
                        return
                    else:
                        # Progress update – yield immediately.
                        msg = json.dumps(message) + "\n"
                        # Add padding to force proxies/CDN to flush the chunk
                        # Uncomment these lines when running on servers that buffer small responses
                        # Such as Github Codespaces
                        # padding = " " * (2048 - len(msg)) + "\n"
                        yield msg  # + padding

                except Empty:
                    # No message yet; check whether the process is still alive.
                    if not proc.is_alive():
                        yield json.dumps(
                            {
                                "type": "error",
                                "message": "Simulation process terminated unexpectedly",
                            }
                        ) + "\n"
                        return
                    # Otherwise keep waiting for the next message.

        except Exception as e:
            import traceback

            error_traceback = traceback.format_exc()
            print(error_traceback, flush=True)

            yield json.dumps(
                {
                    "type": "error",
                    "message": str(e),
                    "traceback": error_traceback,
                }
            ) + "\n"

        finally:
            # Guarantee the subprocess is not left running if the client
            # disconnects mid-stream or an exception escapes the loop.
            if proc is not None and proc.is_alive():
                proc.kill()
                proc.join(timeout=5)

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/solvers", response_model=AllSolverResultsModel)
def run_solvers(payload: SimulationArgsInput | None = None):  # type: ignore
    try:
        args = payload.model_dump(exclude_none=True) if payload else {}
        args = SimulationArgs.from_mapping(args)

        # Run all solvers in one call
        return solve_all(args)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid solver input: {e}")


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
