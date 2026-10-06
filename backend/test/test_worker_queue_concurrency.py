"""Concurrent claimers retain exclusive, token-fenced ownership of real DB rows."""

from concurrent.futures import ThreadPoolExecutor
from os import getenv
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.schema import CreateSchema, DropSchema

from app.application import jobs
from app.core.settings import Settings
from app.database.base import Base
from app.database.models import Account, Run
from app.database.session import make_engine, make_session_factory


@pytest.fixture(params=("sqlite", "postgresql"))
def queue_database(request, tmp_path):
    """Use a private SQLite file or a disposable schema in the CI PostgreSQL DB."""
    if request.param == "postgresql":
        database_url = getenv("CVT_TEST_POSTGRES_URL")
        if not database_url:
            pytest.skip("Set CVT_TEST_POSTGRES_URL to exercise PostgreSQL queue contention.")
    else:
        database_url = f"sqlite:///{tmp_path / 'queue.sqlite3'}"
    engine = make_engine(database_url)
    schema = None
    try:
        if request.param == "postgresql":
            if engine.dialect.name != "postgresql":
                pytest.fail("CVT_TEST_POSTGRES_URL must refer to a PostgreSQL test database.")
            schema = f"worker_test_{uuid4().hex}"
            with engine.begin() as connection:
                connection.execute(CreateSchema(schema))
            engine = engine.execution_options(schema_translate_map={None: schema})
        Base.metadata.create_all(engine)
        yield make_session_factory(engine)
    finally:
        if schema:
            with engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


@pytest.mark.parametrize("queued_count,claimers", [(1, 5), (5, 8)])
def test_simultaneous_claims_assign_each_run_once(queue_database, queued_count, claimers):
    factory = queue_database
    settings = Settings()
    run_ids = {str(uuid4()) for _ in range(queued_count)}
    with factory.begin() as session:
        for run_id in run_ids:
            # One run per workspace, matching normal queue admission. Only the
            # queue lifecycle runs here, so no solver input or seeds are needed.
            account = Account(name="Concurrent queue test")
            session.add(account)
            session.flush()
            session.add(
                Run(
                    id=run_id,
                    account_id=account.id,
                    input_contract={},
                    contract_hash="0" * 64,
                    cinder_model_version="queue-test",
                    input_schema_version=1,
                    status="queued",
                )
            )

    ready = Barrier(claimers)

    def claim():
        with factory.begin() as session:
            ready.wait(timeout=10)
            run = jobs.claim(session, settings)
            return (run.id, run.worker_token) if run else None

    with ThreadPoolExecutor(max_workers=claimers) as pool:
        futures = [pool.submit(claim) for _ in range(claimers)]
        claims = [future.result(timeout=15) for future in futures]
    accepted = [claim for claim in claims if claim is not None]
    assert len(accepted) == queued_count
    assert {run_id for run_id, _ in accepted} == run_ids
    assert len({token for _, token in accepted}) == queued_count
    assert all(token for _, token in accepted)

    with factory.begin() as session:
        assert jobs.claim(session, settings) is None
        persisted = session.scalars(select(Run)).all()
        assert {(run.id, run.worker_token) for run in persisted} == set(accepted)
        assert all(run.status == "running" for run in persisted)
        for run_id, _ in accepted:
            assert not jobs.finish(
                session,
                run_id,
                "not-the-owning-worker",
                error={"code": "wrong_worker", "message": "Must never be stored."},
            )

    # Even two simultaneous finalizers holding the right token cannot both win.
    run_id, token = accepted[0]
    finalizers_ready = Barrier(2)

    def finish():
        with factory.begin() as session:
            finalizers_ready.wait(timeout=10)
            return jobs.finish(
                session,
                run_id,
                token,
                error={"code": "test_finished", "message": "Controlled completion."},
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(finish) for _ in range(2)]
        assert sum(future.result(timeout=15) for future in futures) == 1
    with factory() as session:
        finished = session.get(Run, run_id)
        assert finished.status == "failed"
        assert finished.worker_token is None
        assert finished.error["code"] == "test_finished"
