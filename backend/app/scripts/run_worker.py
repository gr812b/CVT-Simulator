"""Durable POSIX worker: python -m app.scripts.run_worker [--once]."""

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from sqlalchemy import update

from app.application import jobs
from app.application.auth import aware
from app.core.settings import Settings
from app.database.base import utc_now
from app.database.models import Run
from app.database.session import make_engine, make_session_factory

LOG = logging.getLogger("cinder.worker")


def execute(factory, settings, run):
    token = run.worker_token
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
                    "options": run.execution_options,
                    "runtime_identity": run.runtime_identity,
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
        child = None
        try:
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "app.scripts.run_child",
                    str(input_path),
                    str(output_path),
                ],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            while child.poll() is None:
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
                    child.kill()
                    child.wait()
                    if not stop:
                        terminal = "timed_out"
                        error = {
                            "code": "run_timeout",
                            "message": "The simulation exceeded its wall-clock time limit. Shorten the scenario or review its numerical settings.",
                        }
                    break
                time.sleep(min(settings.worker_poll_seconds, 0.5))
            # The deadline may interrupt output serialization. Classify the exit
            # before attempting to parse any partial output file.
            if error is None and child.returncode in {-signal.SIGALRM, 124}:
                terminal = "timed_out"
                error = {
                    "code": "run_timeout",
                    "message": "The simulation exceeded its wall-clock time limit.",
                }
            elif (
                error is None
                and output_path.exists()
                and output_path.stat().st_size <= settings.run_max_result_bytes
            ):
                payload = json.loads(output_path.read_text())
                result, error = payload.get("result"), payload.get("error")
            if result is None and error is None:
                error = {
                    "code": "worker_process_stopped",
                    "message": "The simulation process stopped without a result (cancellation or resource limit).",
                }
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
