"""Database queue admission, account isolation and fenced lifecycle transitions.

No request or API process owns execution. The account row serializes admission
across tabs and workers, including SQLite where SELECT FOR UPDATE is ineffective.
"""

import copy
import json
import math
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import object_session

from app.application import access
from app.application.auth import aware
from app.application.input_validation import validate_case
from app.core.errors import ApiProblem
from app.database import runs as artifacts
from app.database.base import utc_now
from app.database.experiment_models import RunNotification
from app.database.hashing import canonical_json_hash
from app.database.models import Account, AccountUser, Run, RunArtifact
from app.schemas.runs import RunActivity, RunStatusResponse

ACTIVE = ("queued", "running")


def database_now(session):
    """Lease comparisons share the database clock, not potentially skewed hosts."""
    if session.bind.dialect.name == "postgresql":
        return aware(session.scalar(select(func.clock_timestamp())))
    value = session.scalar(select(func.strftime("%Y-%m-%d %H:%M:%f", "now")))
    return aware(datetime.fromisoformat(value))


def status(run, *, include_provenance=True):
    session = object_session(run)
    position = None
    if run.status == "queued" and session is not None:
        position = 1 + session.scalar(
            select(func.count())
            .select_from(Run)
            .where(
                Run.status == "queued",
                (Run.submitted_at < run.submitted_at)
                | ((Run.submitted_at == run.submitted_at) & (Run.id < run.id)),
            )
        )
    from app.application.authorship import author_name, public_author_id

    return RunStatusResponse(
        author=author_name(session, run.created_by_user_id),
        author_id=public_author_id(session, run.created_by_user_id),
        queue_position=position,
        has_result=bool(run.summary_series),
        id=run.id,
        name=run.name,
        source=run.source,
        status=run.status,
        submitted_at=aware(run.submitted_at),
        started_at=aware(run.started_at) if run.started_at else None,
        completed_at=aware(run.completed_at) if run.completed_at else None,
        error=run.error,
        contract_hash=run.contract_hash,
        cache_entry_id=run.cache_entry_id,
        vehicle_assembly_version_id=run.vehicle_assembly_version_id,
        cinder_package_version=run.cinder_model_version,
        input_schema_version=run.input_schema_version,
        result_contract_version=run.result_contract_version,
        summary_scalars=run.summary_scalars or {},
        parent_run_id=run.parent_run_id,
        provenance=(run.provenance or {}) if include_provenance else {},
        runtime_identity=run.runtime_identity or {},
        cancel_requested_at=aware(run.cancel_requested_at) if run.cancel_requested_at else None,
        deadline_at=aware(run.deadline_at) if run.deadline_at else None,
    )


def validate_limits(case, settings):
    try:
        if len(json.dumps(case, allow_nan=False).encode()) > settings.run_max_input_bytes:
            raise ValueError("Input document is too large.")
        span = case["scenario"]["time_span_s"]
        duration = span[1] - span[0]
        if not 0 < duration <= settings.run_max_duration_seconds:
            raise ValueError(
                f"Simulation duration must be between 0 and {settings.run_max_duration_seconds:g} seconds."
            )
        execution = case["execution"]
        grid = execution["reporting"]["grid"]
        if grid["kind"] == "uniform_time_step":
            step = grid["step_seconds"]
            samples = math.ceil(duration / step) + 1 if step > 0 else math.inf
        else:
            samples = grid.get("count") or math.inf
        if not 2 <= samples <= settings.run_max_report_samples:
            raise ValueError("Reporting grid exceeds the sample limit.")
        integrator = execution["integrator"]
        if (
            not 1e-8 <= integrator["relative_tolerance"] <= 0.1
            or not 1e-12 <= integrator["absolute_tolerance"] <= 0.01
        ):
            raise ValueError("Solver tolerances are outside the supported range.")
        if not 1 <= integrator["maximum_transitions"] <= 2000:
            raise ValueError("Maximum transitions must be between 1 and 2000.")
        if integrator.get("retain_dense_output"):
            raise ValueError("Retaining dense solver output is disabled for queued jobs.")
        road = case.get("shaft_boundaries", {}).get("secondary", {}).get("road_profile", {})
        if len(road.get("segments", [])) > settings.road_max_segments:
            raise ValueError("Road profile exceeds the segment limit.")
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ApiProblem(422, "run_limits", str(exc)) from exc


def existing_request(session, principal, request_key, request_payload):
    row = session.scalar(
        select(Run).where(Run.account_id == principal.account_id, Run.request_key == request_key)
    )
    if row and row.request_hash != canonical_json_hash(request_payload):
        raise ApiProblem(
            409,
            "idempotency_conflict",
            "This request key already belongs to a different submission.",
        )
    return row


def check_available(session, account_id, settings):
    active = session.scalar(select(Run).where(Run.account_id == account_id, Run.status.in_(ACTIVE)))
    if active:
        now = database_now(session)
        expired = (
            active.status == "queued"
            and aware(active.submitted_at) + timedelta(seconds=settings.run_queue_timeout_seconds)
            < now
        ) or (
            active.status == "running"
            and active.deadline_at is not None
            and aware(active.deadline_at) + timedelta(seconds=settings.run_recovery_grace_seconds)
            < now
        )
        if not expired:
            raise ApiProblem(
                409,
                "run_already_active",
                "This workspace already has a queued or running simulation.",
                {"run_id": active.id},
            )


def submit(
    session,
    principal,
    settings,
    gateway,
    *,
    request_key,
    request_payload,
    case,
    provenance=None,
    name="Simulation",
    source="direct",
    parent_run_id=None,
    options=None,
):
    principal.require_write()
    existing = existing_request(session, principal, request_key, request_payload)
    if existing:
        return existing
    check_available(session, principal.account_id, settings)
    validate_limits(case, settings)
    try:
        validation = validate_case(case)
    except (ValueError, TypeError, KeyError) as exc:
        raise ApiProblem(422, "invalid_simulation_case", str(exc)) from exc
    if not validation["is_valid"]:
        raise ApiProblem(
            422,
            "invalid_simulation_case",
            "The simulation input is invalid.",
            validation,
        )
    # Acquire the write lock only after potentially expensive validation.
    session.execute(
        update(Account).where(Account.id == principal.account_id).values(updated_at=utc_now())
    )
    existing = existing_request(session, principal, request_key, request_payload)
    if existing:
        return existing
    recover(session, settings, principal.account_id)
    active = session.scalar(
        select(Run).where(Run.account_id == principal.account_id, Run.status.in_(ACTIVE))
    )
    if active:
        raise ApiProblem(
            409,
            "run_already_active",
            "This workspace already has a queued or running simulation.",
            {"run_id": active.id},
        )
    now = database_now(session)
    count = session.scalar(
        select(func.count())
        .select_from(Run)
        .where(
            Run.account_id == principal.account_id,
            Run.submitted_at > now - timedelta(seconds=settings.run_submission_window_seconds),
        )
    )
    if count >= settings.run_submission_limit:
        raise ApiProblem(
            429,
            "run_rate_limit",
            "Too many recent simulations. Please wait before submitting another.",
            {"retry_after_seconds": settings.run_submission_window_seconds},
        )
    runtime = gateway.runtime_identity()
    options = options or {
        "include_reported_segments": False,
        "include_raw_trace": False,
        "execution_profile": "default",
    }
    frozen = copy.deepcopy(case)
    provenance = copy.deepcopy(provenance or {})
    canonical = {
        k: frozen[k]
        for k in (
            "schema_version",
            "document_type",
            "assembly",
            "shaft_boundaries",
            "host",
            "scenario",
            "execution",
        )
        if k in frozen
    }
    row = Run(
        account_id=principal.account_id,
        created_by_user_id=principal.user_id,
        name=name,
        source=source,
        request_key=request_key,
        request_hash=canonical_json_hash(request_payload),
        parent_run_id=parent_run_id,
        input_contract=frozen,
        contract_hash=canonical_json_hash(
            {"input": canonical, "runtime": runtime, "options": options}
        ),
        cinder_model_version=runtime["package_version"],
        input_schema_version=runtime["simulation_case_schema_version"],
        result_contract_version=runtime["simulation_result_contract_version"],
        status="queued",
        submitted_at=now,
        runtime_identity=runtime,
        provenance=provenance,
        execution_options=copy.deepcopy(options),
        vehicle_assembly_version_id=provenance.get("setup_revision_id"),
        engine_version_id=provenance.get("engine_revision_id"),
        cvt_design_version_id=provenance.get("cvt_revision_id"),
        output_system_version_id=provenance.get("output_revision_id"),
        tune_snapshot=provenance.get("tune_values", {}),
        load_case_snapshot=provenance.get("scenario", {}),
        execution_snapshot=case["execution"],
    )
    session.add(row)
    session.flush()
    return row


def _notify(session, run):
    for user_id in session.scalars(
        select(AccountUser.user_id).where(AccountUser.account_id == run.account_id)
    ):
        session.add(RunNotification(account_id=run.account_id, user_id=user_id, run_id=run.id))


def recover(session, settings, account_id=None):
    """Never release a running slot until the child's hard deadline has passed.

    The child arms an OS-enforced absolute deadline before importing CINDER.
    Even a dead parent cannot leave an orphan computing after this grace period.
    """
    now = database_now(session)
    expired = (
        (Run.status == "running")
        & (Run.deadline_at < now - timedelta(seconds=settings.run_recovery_grace_seconds))
    ) | (
        (Run.status == "queued")
        & (Run.submitted_at < now - timedelta(seconds=settings.run_queue_timeout_seconds))
    )
    stmt = select(Run).where(expired)
    if account_id:
        stmt = stmt.where(Run.account_id == account_id)
    for run in session.scalars(stmt):
        values = {
            "status": "failed",
            "completed_at": now,
            "worker_token": None,
            "error": {
                "code": "worker_interrupted" if run.status == "running" else "queue_timeout",
                "message": "The worker did not finish within its deadline. You can retry as a new run.",
            },
        }
        if session.execute(
            update(Run)
            .where(Run.id == run.id, expired)
            .values(**values)
            .execution_options(synchronize_session=False)
        ).rowcount:
            session.refresh(run)
            if run.summary_series:
                saved = artifacts.get_database_run_result(session, run.id)
                saved["metrics"].update(completed=False, termination_reason=run.error["code"])
                _save_result(session, run, saved)
            _notify(session, run)
    session.flush()
    session.expire_all()


def claim(session, settings):
    recover(session, settings)
    for run_id in session.scalars(
        select(Run.id).where(Run.status == "queued").order_by(Run.submitted_at, Run.id).limit(10)
    ):
        now, token = database_now(session), str(uuid4())
        if session.execute(
            update(Run)
            .where(Run.id == run_id, Run.status == "queued")
            .values(
                status="running",
                worker_token=token,
                started_at=now,
                heartbeat_at=now,
                deadline_at=now + timedelta(seconds=settings.run_timeout_seconds),
            )
        ).rowcount:
            session.flush()
            return session.get(Run, run_id)
    return None


def cancel(session, principal, run_id):
    principal.require_write()
    run = access.owned(session.get(Run, run_id), principal)
    now = utc_now()
    if session.execute(
        update(Run)
        .where(Run.id == run.id, Run.status == "queued")
        .values(
            status="cancelled",
            cancel_requested_at=now,
            completed_at=now,
        )
        .execution_options(synchronize_session=False)
    ).rowcount:
        _notify(session, run)
    else:
        session.execute(
            update(Run)
            .where(
                Run.id == run.id,
                Run.status == "running",
                Run.cancel_requested_at.is_(None),
            )
            .values(cancel_requested_at=now)
            .execution_options(synchronize_session=False)
        )
    session.refresh(run)
    return run


def _save_result(session, run, result):
    """Replace the durable full result and preview in the caller's transaction."""
    artifacts.verify_result_contract(result, expected_version=run.result_contract_version)
    preview = artifacts.build_preview_from_result(result)
    session.execute(delete(RunArtifact).where(RunArtifact.run_id == run.id))
    session.add(artifacts.create_result_artifact(run_id=run.id, cache_entry_id=None, result=result))
    session.add(
        artifacts.create_preview_artifact(run_id=run.id, cache_entry_id=None, preview=preview)
    )
    run.summary_scalars = artifacts.summary_scalars(result)
    run.summary_series = preview


def checkpoint(session, run_id, token, result):
    if not session.execute(
        update(Run)
        .where(
            Run.id == run_id,
            Run.status == "running",
            Run.worker_token == token,
        )
        .values(heartbeat_at=utc_now())
    ).rowcount:
        return False
    run = session.get(Run, run_id, populate_existing=True)
    _save_result(session, run, result)
    session.flush()
    return True


def finish(session, run_id, token, *, result=None, error=None, terminal="failed"):
    # A write CAS also serializes completion with cancellation before reading it.
    if not session.execute(
        update(Run)
        .where(Run.id == run_id, Run.status == "running", Run.worker_token == token)
        .values(heartbeat_at=utc_now())
    ).rowcount:
        return False
    run = session.get(Run, run_id, populate_existing=True)
    if run.cancel_requested_at:
        error, terminal = None, "cancelled"
    if result is not None:
        if error or terminal == "cancelled":
            result = copy.deepcopy(result)
            result["metrics"].update(
                completed=False, termination_reason=(error or {}).get("code", terminal)
            )
        _save_result(session, run, result)
        if error is None and terminal != "cancelled":
            terminal = "completed"
    run.status, run.error, run.completed_at, run.worker_token = (
        terminal,
        error,
        utc_now(),
        None,
    )
    _notify(session, run)
    session.flush()
    return True


def activity(session, principal, settings):
    recover(session, settings, principal.account_id)
    active = session.scalar(
        select(Run).where(Run.account_id == principal.account_id, Run.status.in_(ACTIVE))
    )
    condition = (RunNotification.account_id == principal.account_id) & RunNotification.read_at.is_(
        None
    )
    condition = condition & (RunNotification.user_id == principal.user_id)
    notices = session.scalars(
        select(RunNotification)
        .where(condition)
        .order_by(RunNotification.created_at.desc())
        .limit(50)
    )
    return RunActivity(
        active=status(active, include_provenance=False) if active else None,
        unread=[
            {
                "id": notice.id,
                "created_at": aware(notice.created_at),
                "run": status(session.get(Run, notice.run_id), include_provenance=False),
            }
            for notice in notices
        ],
        unread_count=session.scalar(
            select(func.count()).select_from(RunNotification).where(condition)
        ),
    )
