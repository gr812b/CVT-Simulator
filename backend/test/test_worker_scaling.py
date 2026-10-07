"""Bounded concurrent scheduling uses real durable claims and separate sessions."""

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import threading
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.application import jobs
from app.core.settings import Settings
from app.database.base import Base, utc_now
from app.database.models import Account, Run
from app.database.session import make_engine, make_session_factory
from app.scripts import run_worker


class WorkerHarness:
    def __init__(self, tmp_path, monkeypatch):
        self.settings = Settings(
            database_url=f"sqlite:///{tmp_path / 'queue.sqlite3'}", worker_poll_seconds=0.01
        )
        self.engine = make_engine(self.settings.database_url)
        Base.metadata.create_all(self.engine)
        self.factory = make_session_factory(self.engine)
        self.condition = threading.Condition()
        self.stopping = threading.Event()
        self.started = []
        self.active = set()
        self.released = set()
        self.release_all = False
        self.peak = 0
        self.thread = None
        self.done = Future()
        monkeypatch.setattr(run_worker, "execute", self.execute)

    def enqueue(self, count):
        now, ids = utc_now(), []
        with self.factory.begin() as session:
            for index in range(count):
                account = Account(name=f"Workspace {uuid4()}")
                session.add(account)
                session.flush()
                run = Run(
                    account_id=account.id,
                    input_contract={},
                    contract_hash="0" * 64,
                    cinder_model_version="test",
                    input_schema_version=1,
                    status="queued",
                    submitted_at=now + timedelta(microseconds=index),
                )
                session.add(run)
                session.flush()
                ids.append(run.id)
        return ids

    def execute(self, factory, settings, run):
        with self.condition:
            self.started.append(run.id)
            self.active.add(run.id)
            self.peak = max(self.peak, len(self.active))
            self.condition.notify_all()
            assert self.condition.wait_for(
                lambda: self.release_all or run.id in self.released, timeout=10
            ), "The test did not release its controlled run."
        with factory.begin() as session:
            jobs.finish(session, run.id, run.worker_token, terminal="cancelled")
        with self.condition:
            self.active.remove(run.id)
            self.condition.notify_all()

    def start(self, *, capacity=2, once=False, ready=None):
        self.settings = replace(self.settings, worker_max_concurrency=capacity)

        def supervise():
            try:
                run_worker.serve(self.factory, self.settings, self.stopping, once=once, ready=ready)
            except BaseException as exc:
                self.done.set_exception(exc)
            else:
                self.done.set_result(None)

        self.thread = threading.Thread(target=supervise)
        self.thread.start()

    def wait_started(self, count):
        with self.condition:
            assert self.condition.wait_for(lambda: len(self.started) >= count, timeout=5)

    def wait_active(self, count):
        with self.condition:
            assert self.condition.wait_for(lambda: len(self.active) == count, timeout=5)

    def assert_no_more_starts(self, count):
        with self.condition:
            assert not self.condition.wait_for(lambda: len(self.started) > count, timeout=0.05)

    def release(self, *ids):
        with self.condition:
            self.released.update(ids)
            self.condition.notify_all()

    def statuses(self):
        with self.factory() as session:
            return dict(session.execute(select(Run.id, Run.status)).all())

    def close(self):
        self.stopping.set()
        with self.condition:
            self.release_all = True
            self.condition.notify_all()
        if self.thread is not None:
            self.thread.join(timeout=5)
            assert not self.thread.is_alive(), "The supervisor did not drain and stop."
        self.engine.dispose()


@pytest.fixture
def worker(tmp_path, monkeypatch):
    harness = WorkerHarness(tmp_path, monkeypatch)
    try:
        yield harness
    finally:
        harness.close()


def test_capacity_is_bounded_and_free_slots_refill_without_prefetch(worker):
    ids = worker.enqueue(5)
    worker.start(capacity=2)
    worker.wait_started(2)
    worker.assert_no_more_starts(2)
    assert worker.started == ids[:2]
    assert worker.statuses() == dict(zip(ids, ["running", "running", *(["queued"] * 3)]))

    worker.release(ids[0])
    worker.wait_started(3)
    worker.assert_no_more_starts(3)
    assert worker.started == ids[:3]
    assert worker.statuses() == dict(
        zip(ids, ["cancelled", "running", "running", "queued", "queued"])
    )

    worker.release(*ids)
    worker.wait_started(5)
    worker.wait_active(0)
    worker.stopping.set()
    worker.done.result(timeout=5)
    assert worker.peak == 2
    assert set(worker.statuses().values()) == {"cancelled"}


def test_idle_worker_takes_new_demand_and_returns_to_no_active_runs(worker):
    worker.start(capacity=3)
    worker.assert_no_more_starts(0)
    ids = worker.enqueue(1)
    worker.wait_started(1)
    assert worker.active == {ids[0]}
    worker.release(*ids)
    worker.wait_active(0)
    worker.assert_no_more_starts(1)
    assert not worker.done.done()


def test_shutdown_drains_current_runs_and_leaves_waiting_runs_queued(worker):
    ids = worker.enqueue(3)
    worker.start(capacity=2)
    worker.wait_started(2)
    worker.stopping.set()
    assert not worker.done.done()

    worker.release(ids[0])
    worker.wait_active(1)
    worker.assert_no_more_starts(2)
    assert not worker.done.done()
    worker.release(ids[1])
    worker.done.result(timeout=5)
    assert worker.statuses() == dict(zip(ids, ["cancelled", "cancelled", "queued"]))


def test_once_claims_at_most_one_even_with_a_larger_cap_and_waits_for_it(worker):
    ids = worker.enqueue(2)
    worker.start(capacity=5, once=True)
    worker.wait_started(1)
    worker.assert_no_more_starts(1)
    assert not worker.done.done()
    worker.release(ids[0])
    worker.done.result(timeout=5)
    assert worker.statuses() == dict(zip(ids, ["cancelled", "queued"]))


def test_once_with_an_empty_queue_exits_without_executing(worker):
    worker.start(capacity=5, once=True)
    worker.done.result(timeout=5)
    assert worker.started == []


def test_readiness_pauses_claiming_while_current_runs_continue(worker):
    ids = worker.enqueue(3)
    ready = threading.Event()
    worker.start(capacity=2, ready=ready.is_set)
    worker.assert_no_more_starts(0)
    assert set(worker.statuses().values()) == {"queued"}

    ready.set()
    worker.wait_started(2)
    ready.clear()
    worker.release(*ids[:2])
    worker.wait_active(0)
    worker.assert_no_more_starts(2)
    assert worker.statuses()[ids[2]] == "queued"
    ready.set()
    worker.wait_started(3)
    worker.release(ids[2])


def test_signal_during_claim_rolls_back_before_starting_a_child(worker, monkeypatch):
    ids = worker.enqueue(1)
    claim = jobs.claim

    def stop_during_claim(session, settings):
        run = claim(session, settings)
        worker.stopping.set()
        return run

    monkeypatch.setattr(jobs, "claim", stop_during_claim)
    run_worker.serve(worker.factory, worker.settings, worker.stopping)
    assert worker.started == []
    assert worker.statuses() == {ids[0]: "queued"}
    with worker.factory() as session:
        run = session.get(Run, ids[0])
        assert run.worker_token is None
        assert run.started_at is None


def test_unexpected_execution_failure_is_reported_and_slot_is_reused(worker, monkeypatch):
    ids = worker.enqueue(2)

    def execute(factory, settings, run):
        if run.id == ids[0]:
            raise OSError("Temporary input directory is unavailable")
        worker.execute(factory, settings, run)

    monkeypatch.setattr(run_worker, "execute", execute)
    worker.start(capacity=1)
    worker.wait_started(1)
    with worker.factory() as session:
        failed = session.get(Run, ids[0])
        assert failed.status == "failed"
        assert failed.worker_token is None
        assert failed.error["code"] == "worker_failure"
    assert worker.started == [ids[1]]
    worker.release(ids[1])


def test_unexpected_failure_cannot_finish_a_different_workers_claim(worker, monkeypatch):
    (run_id,) = worker.enqueue(1)
    replacement_token = str(uuid4())

    def execute(factory, settings, run):
        with factory.begin() as session:
            session.execute(
                update(Run).where(Run.id == run.id).values(worker_token=replacement_token)
            )
        raise OSError("The original supervisor failed")

    monkeypatch.setattr(run_worker, "execute", execute)
    run_worker.serve(worker.factory, worker.settings, worker.stopping, once=True)
    with worker.factory() as session:
        run = session.get(Run, run_id)
        assert run.status == "running"
        assert run.worker_token == replacement_token
        assert run.error is None


def test_failed_submission_does_not_launch_enqueued_work_or_leave_a_live_claim(worker, monkeypatch):
    (run_id,) = worker.enqueue(1)

    class RejectedSubmission(ThreadPoolExecutor):
        def submit(self, *args, **kwargs):
            super().submit(*args, **kwargs)
            raise RuntimeError("Thread creation failed after enqueue")

    monkeypatch.setattr(run_worker, "ThreadPoolExecutor", RejectedSubmission)
    with pytest.raises(RuntimeError, match="Thread creation failed"):
        run_worker.serve(worker.factory, worker.settings, worker.stopping, once=True)
    assert worker.started == []
    with worker.factory() as session:
        run = session.get(Run, run_id)
        assert run.status == "failed"
        assert run.worker_token is None
        assert run.error["code"] == "worker_failure"


def test_claim_exception_still_drains_previously_accepted_runs(worker, monkeypatch):
    ids = worker.enqueue(2)
    claim = jobs.claim
    calls = 0

    def failing_claim(session, settings):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise RuntimeError("Database connection lost")
        return claim(session, settings)

    monkeypatch.setattr(jobs, "claim", failing_claim)
    worker.start(capacity=2)
    worker.wait_started(1)
    assert not worker.done.done()
    worker.release(ids[0])
    with pytest.raises(RuntimeError, match="Database connection lost"):
        worker.done.result(timeout=5)
    assert worker.statuses() == dict(zip(ids, ["cancelled", "queued"]))
