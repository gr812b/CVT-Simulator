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
from pathlib import Path

import psutil
from sqlalchemy import update

from app.application import jobs
from app.application.auth import aware
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
        remaining = (
            aware(run.deadline_at) - jobs.database_now(session)
        ).total_seconds()
    deadline_monotonic = reference + max(0, remaining)
    with tempfile.TemporaryDirectory(prefix="cinder-job-") as directory:
        input_path, output_path = (
            Path(directory) / "input.json",
            Path(directory) / "output.json",
        )
        input_path.write_text(
            json.dumps(
                {
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
            elif error is None and child.returncode != 0:
                error = stopped_error(child.returncode)
            elif (
                error is None
                and output_path.exists()
                and output_path.stat().st_size <= settings.run_max_result_bytes
            ):
                payload = json.loads(output_path.read_text())
                result, error = payload.get("result", result), payload.get("error")
            if result is None and error is None and not stopped_by_supervisor:
                error = stopped_error(child.returncode)
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
                    "Run %s failed: %s (child exit %s)",
                    run.id,
                    error["code"],
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
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        try:
            require_current_schema(engine)
        except DatabaseNotReadyError as exc:
            parser.error(str(exc))
        while not stopping:
            with factory.begin() as session:
                run = jobs.claim(session, settings)
            if run:
                LOG.info("Executing run %s", run.id)
                execute(factory, settings, run)
            elif not args.once:
                time.sleep(settings.worker_poll_seconds)
            if args.once:
                break
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
