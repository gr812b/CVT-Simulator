"""Durable POSIX worker: python -m app.scripts.run_worker [--once]."""

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path

import psutil
from sqlalchemy import update

from app.application import jobs
from app.application.auth import aware
from app.core.deployment import ApiReadinessGate
from app.core.settings import Settings
from app.database.base import utc_now
from app.database.maintenance import DatabaseNotReadyError, require_current_schema
from app.database.models import Run
from app.database.session import make_engine, make_session_factory

LOG = logging.getLogger("cinder.worker")


def capture_stderr(stream, tail):
    """Drain continuously, retaining at most 16 KiB; never block the solver pipe."""
    with stream:
        while chunk := stream.read(4096):
            tail.extend(chunk)
            del tail[:-16384]


def stopped_error(returncode):
    if returncode == 125:
        return {
            "code": "worker_parent_changed",
            "message": "The simulation lost its worker during startup. Retry as a new run; see the worker terminal for details.",
        }
    if returncode == -signal.SIGXFSZ:
        return {
            "code": "run_result_size_limit",
            "message": "The result exceeded the storage limit. Reduce reporting detail or shorten the scenario.",
        }
    if returncode is not None and returncode < 0:
        try:
            reason = signal.Signals(-returncode).name
        except ValueError:
            reason = f"signal {-returncode}"
        message = f"The simulation process was terminated by {reason}. See the worker terminal for details."
        if returncode == -signal.SIGKILL:
            message += " The operating system may have stopped it for memory pressure."
    else:
        message = f"The simulation process exited with code {returncode} before returning a result. See the worker terminal for the startup or runtime error."
    return {"code": "worker_process_stopped", "message": message}


def read_child_payload(output_path, *, returncode, result_bytes):
    """Read the atomic completion envelope independently of the process exit code.

    A handled failure exits nonzero and carries its own precise error. A lone
    checkpoint is never proof of successful completion.
    """
    if not output_path.exists():
        return None, stopped_error(returncode)
    if output_path.stat().st_size > result_bytes:
        return None, {
            "code": "run_result_size_limit",
            "message": "The result exceeded the storage limit. Any earlier saved checkpoint is still available.",
        }
    try:
        payload = json.loads(output_path.read_text())
        if not isinstance(payload, dict):
            raise ValueError("Completion envelope must be an object.")
        result, error = payload.get("result"), payload.get("error")
        if result is not None and not isinstance(result, dict):
            raise ValueError("Completion result must be an object.")
        if error is not None and (
            not isinstance(error, dict)
            or not isinstance(error.get("code"), str)
            or not isinstance(error.get("message"), str)
        ):
            raise ValueError("Completion error must contain a code and message.")
        if result is None and error is None:
            raise ValueError("Completion envelope contains no result or error.")
    except (OSError, UnicodeError, ValueError):
        LOG.exception("Could not read the simulation child's completion envelope")
        return None, {
            "code": "child_protocol_error",
            "message": "The worker received an incomplete or unreadable response from the simulation. Any earlier saved checkpoint is still available.",
        }
    if error is None and returncode != 0:
        error = stopped_error(returncode)
    return result, error


def execute(factory, settings, run):
    token = run.worker_token
    scenario = (run.provenance or {}).get("scenario", {})
    stops = scenario.get("stops", {})
    policy = {}
    if stops.get("mode") == "course":
        policy = {
            "finish_m": run.provenance["resolved_road"]["length_m"],
            "rollback_m": stops.get("rollback_m"),
            "no_progress_s": stops.get("no_progress_s"),
        }
    error, result, terminal = None, None, "failed"
    # Start the local budget before the DB round trip, so delay cannot extend it.
    reference = time.monotonic()
    with factory() as session:
        remaining = (aware(run.deadline_at) - jobs.database_now(session)).total_seconds()
    deadline_monotonic = reference + max(0, remaining)
    with tempfile.TemporaryDirectory(prefix="cinder-job-") as directory:
        input_path, output_path = (
            Path(directory) / "input.json",
            Path(directory) / "output.json",
        )
        input_path.write_text(
            json.dumps(
                {
                    "run_id": run.id,
                    "input": run.input_contract,
                    "course_policy": policy,
                    "options": run.execution_options,
                    "runtime_identity": run.runtime_identity,
                    "worker_pid": os.getpid(),
                    "deadline_monotonic": deadline_monotonic,
                    "memory_bytes": settings.run_memory_limit_mb * 1024 * 1024,
                    "result_bytes": settings.run_max_result_bytes,
                },
                allow_nan=False,
            )
        )
        env = {
            **os.environ,
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        }
        checkpoint_path = Path(directory) / "checkpoint.json"
        checkpoint_stamp = None

        def retain_checkpoint():
            nonlocal checkpoint_stamp, result
            if not checkpoint_path.exists():
                return
            stamp = checkpoint_path.stat().st_mtime_ns
            if stamp == checkpoint_stamp:
                return
            if checkpoint_path.stat().st_size > settings.run_max_result_bytes:
                return
            latest = json.loads(checkpoint_path.read_text())
            with factory.begin() as session:
                jobs.checkpoint(session, run.id, token, latest)
            checkpoint_stamp, result = stamp, latest

        child = None
        stopped_by_supervisor = False
        stderr_thread = None
        stderr_tail = bytearray()
        try:
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "app.scripts.run_child",
                    str(input_path),
                    str(output_path),
                ],
                cwd=Path(__file__).resolve().parents[2],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            stderr_thread = threading.Thread(
                target=capture_stderr, args=(child.stderr, stderr_tail), daemon=True
            )
            stderr_thread.start()
            try:
                monitored = psutil.Process(child.pid)
            except psutil.NoSuchProcess:
                monitored = None
            while child.poll() is None:
                retain_checkpoint()
                with factory.begin() as session:
                    current = session.get(Run, run.id)
                    stop = (
                        current is None
                        or current.worker_token != token
                        or current.status != "running"
                        or current.cancel_requested_at is not None
                    )
                    if not stop:
                        session.execute(
                            update(Run)
                            .where(Run.id == run.id, Run.worker_token == token)
                            .values(heartbeat_at=utc_now())
                        )
                if stop or time.monotonic() >= deadline_monotonic:
                    stopped_by_supervisor = stop
                    child.kill()
                    child.wait()
                    if not stop:
                        terminal = "timed_out"
                        error = {
                            "code": "run_timeout",
                            "message": "The simulation exceeded its wall-clock time limit. Shorten the scenario or review its numerical settings.",
                        }
                    break
                try:
                    resident_bytes = monitored.memory_info().rss if monitored else 0
                except psutil.NoSuchProcess:
                    # Exit can race with sampling; the result/exit code below owns it.
                    resident_bytes = 0
                if resident_bytes > settings.run_memory_limit_mb * 1024 * 1024:
                    child.kill()
                    child.wait()
                    error = {
                        "code": "run_memory_limit",
                        "message": "The simulation exceeded its memory budget. Shorten the scenario or reduce reporting detail.",
                    }
                    break
                time.sleep(min(settings.worker_poll_seconds, 0.5))
            retain_checkpoint()
            # The deadline may interrupt output serialization. Classify the exit
            # before attempting to parse any partial output file.
            if stopped_by_supervisor:
                # finish() owns cancellation and rejects a stale worker token.
                pass
            elif error is None and child.returncode in {-signal.SIGALRM, 124}:
                terminal = "timed_out"
                error = {
                    "code": "run_timeout",
                    "message": "The simulation exceeded its wall-clock time limit.",
                }
            elif error is None:
                completed_result, error = read_child_payload(
                    output_path,
                    returncode=child.returncode,
                    result_bytes=settings.run_max_result_bytes,
                )
                if completed_result is not None:
                    result = completed_result
        except Exception:
            LOG.exception("Run %s could not execute", run.id)
            error = {
                "code": "worker_failure",
                "message": "The worker could not finish this run. You can retry as a new run.",
            }
        finally:
            # Completion/slot release is strictly after wait(), including shutdown.
            if child is not None and child.poll() is None:
                child.kill()
                child.wait()
            if stderr_thread:
                stderr_thread.join(timeout=2)
            if error:
                LOG.error(
                    "Run %s failed: %s — %s (child exit %s)",
                    run.id,
                    error["code"],
                    error["message"],
                    child.returncode if child else None,
                )
                if stderr_tail:
                    LOG.error(
                        "Run %s child stderr (last 16 KiB):\n%s",
                        run.id,
                        stderr_tail.decode("utf-8", errors="replace"),
                    )
        try:
            with factory.begin() as session:
                jobs.finish(
                    session,
                    run.id,
                    token,
                    result=result,
                    error=error,
                    terminal=terminal,
                )
        except Exception:
            LOG.exception("Run %s result could not be persisted", run.id)
            with factory.begin() as session:
                jobs.finish(
                    session,
                    run.id,
                    token,
                    error={
                        "code": "result_persistence_failed",
                        "message": "The result could not be stored. Retry as a new run.",
                    },
                )


def fail_claimed_run(factory, run):
    """Release only this worker's claim, retaining any durable checkpoint."""
    try:
        with factory.begin() as session:
            jobs.finish(
                session,
                run.id,
                run.worker_token,
                error={
                    "code": "worker_failure",
                    "message": "The worker could not finish this run. You can retry as a new run.",
                },
            )
    except Exception:
        # Deadline recovery remains the fallback if the database is unavailable.
        LOG.exception("Run %s failure could not be persisted", run.id)


def execute_submitted(factory, settings, run, accepted):
    # ThreadPoolExecutor can enqueue work before failing to start a new thread.
    # Do not start its child until submit() has returned successfully.
    if accepted.result():
        LOG.info("Executing run %s", run.id)
        execute(factory, settings, run)


def serve(factory, settings, stopping, *, once=False, ready=None):
    """Claim on demand up to the cap, then drain accepted runs on shutdown.

    Pool threads only supervise; each simulation still has its own bounded OS
    process. There is no prefetched queue and no simulation process when idle.
    """
    pending = {}

    def complete(future, run):
        try:
            future.result()
        except Exception:
            LOG.exception("Run %s failed outside child supervision", run.id)
            fail_claimed_run(factory, run)

    LOG.info("Worker started; maximum concurrent simulations: %s", settings.worker_max_concurrency)
    with ThreadPoolExecutor(
        max_workers=settings.worker_max_concurrency, thread_name_prefix="cinder-run"
    ) as pool:
        try:
            while not stopping.is_set():
                for future in list(pending):
                    if future.done():
                        complete(future, pending.pop(future))
                if len(pending) >= settings.worker_max_concurrency:
                    stopping.wait(settings.worker_poll_seconds)
                    continue
                if ready is not None and not ready():
                    if once:
                        break
                    stopping.wait(settings.worker_poll_seconds)
                    continue
                with factory.begin() as session:
                    # A signal can arrive while readiness or claim queries block.
                    if stopping.is_set():
                        break
                    run = jobs.claim(session, settings)
                    if stopping.is_set():
                        session.rollback()
                        break
                if run is None:
                    if once:
                        break
                    stopping.wait(settings.worker_poll_seconds)
                    continue
                accepted = Future()
                try:
                    future = pool.submit(execute_submitted, factory, settings, run, accepted)
                    pending[future] = run
                except BaseException:
                    accepted.set_result(False)
                    LOG.exception("Run %s could not be submitted to the worker pool", run.id)
                    fail_claimed_run(factory, run)
                    raise
                else:
                    accepted.set_result(True)
                if once:
                    break
        finally:
            if pending:
                LOG.info("Waiting for %s accepted run(s) to finish", len(pending))
            for future in as_completed(pending):
                complete(future, pending[future])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once", action="store_true", help="Claim at most one queued job, then exit."
    )
    args = parser.parse_args()
    if os.name != "posix":
        parser.error(
            "The worker requires POSIX hard-deadline support. Run it in the Linux backend container."
        )
    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_environment()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    stopping = threading.Event()

    def stop(_signum, _frame):
        stopping.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        try:
            gate = ApiReadinessGate(settings.worker_api_url) if settings.worker_api_url else None
        except ValueError as exc:
            parser.error(str(exc))
        schema_checked = False

        def ready():
            nonlocal schema_checked
            if gate is not None and not gate():
                return False
            if not schema_checked:
                require_current_schema(engine)
                schema_checked = True
            return True

        try:
            if gate is None:
                ready()
            serve(factory, settings, stopping, once=args.once, ready=ready)
        except DatabaseNotReadyError as exc:
            parser.error(str(exc))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
