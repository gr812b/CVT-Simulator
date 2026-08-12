"""Database-backed run submission, cache, and result retrieval helpers."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.cinder_gateway import CinderGateway
from app.core.errors import ApiProblem, RunNotFoundError
from app.database.base import utc_now
from app.database.hashing import canonical_json_hash
from app.database.models import Run, RunArtifact, RunCacheEntry, VehicleAssemblyVersion
from app.database.resolver import resolve_simulation_case
from app.database.run_previews import DEFAULT_PREVIEW_PROFILE, build_run_preview

try:  # pragma: no cover - covered indirectly when CINDER is importable.
    from cinder import __version__ as CINDER_MODEL_VERSION
except Exception:  # pragma: no cover - defensive for docs/import-only tooling.
    CINDER_MODEL_VERSION = "unknown"

JsonDict = dict[str, Any]


@dataclass(frozen=True, slots=True)
class SubmittedLibraryRun:
    """A completed or failed persisted library run."""

    run: Run
    cache_hit: bool


class LibraryRunError(ValueError):
    """Raised when a database-backed run cannot be submitted cleanly."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        code: str = "library_run_request_invalid",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


EXECUTABLE_DOCUMENT_KEYS = (
    "schema_version",
    "document_type",
    "assembly",
    "input_boundary",
    "output_boundary",
    "scenario",
    "execution",
)


def submit_library_run(
    session: Session,
    *,
    gateway: CinderGateway,
    account_id: str,
    vehicle_assembly_version_id: str,
    tune_id: str | None = None,
    load_case_id: str | None = None,
    execution_preset_id: str | None = None,
    created_by_user_id: str | None = None,
    include_reported_segments: bool = False,
    include_raw_trace: bool = False,
) -> SubmittedLibraryRun:
    """Resolve, cache-check, execute, and persist one library-backed run.

    The existing direct-contract endpoint remains available for debugging and
    comparison. This path captures the full resolved input contract, summary
    fields, a cache row keyed by the executable contract, and an inline full
    result artifact suitable for local development and V1 retrieval.
    """

    assembly_version = session.get(VehicleAssemblyVersion, vehicle_assembly_version_id)
    if assembly_version is None:
        raise LibraryRunError(
            f"Unknown vehicle assembly version {vehicle_assembly_version_id!r}.",
            status_code=404,
            code="library_run_source_not_found",
        )

    try:
        document = resolve_simulation_case(
            session,
            vehicle_assembly_version_id=vehicle_assembly_version_id,
            tune_id=tune_id,
            load_case_id=load_case_id,
            execution_preset_id=execution_preset_id,
        )
    except ValueError as exc:
        raise LibraryRunError(
            str(exc),
            status_code=_resolution_error_status(str(exc)),
            code="library_run_resolution_failed",
        ) from exc
    contract_hash = canonical_json_hash(executable_contract(document))
    document["contract_hash"] = contract_hash
    cinder_model_version = str(CINDER_MODEL_VERSION)
    contract_schema_version = int(document.get("schema_version", 1))

    validation = gateway.validate_simulation_case(document)
    if not bool(validation.get("is_valid")):
        raise ApiProblem(
            422,
            "simulation_case_invalid",
            "The resolved database simulation case failed CINDER validation.",
            {"validation": validation},
        )

    cached = _completed_cache_entry(
        session,
        contract_hash=contract_hash,
        cinder_model_version=cinder_model_version,
        contract_schema_version=contract_schema_version,
    )
    if cached is not None:
        run = _create_completed_cache_hit_run(
            session,
            account_id=account_id,
            created_by_user_id=created_by_user_id,
            assembly_version=assembly_version,
            tune_id=tune_id,
            load_case_id=load_case_id,
            execution_preset_id=execution_preset_id,
            input_contract=document,
            contract_hash=contract_hash,
            cinder_model_version=cinder_model_version,
            contract_schema_version=contract_schema_version,
            cache_entry=cached,
        )
        return SubmittedLibraryRun(run=run, cache_hit=True)

    existing_cache_entry = _cache_entry_by_contract(
        session,
        contract_hash=contract_hash,
        cinder_model_version=cinder_model_version,
        contract_schema_version=contract_schema_version,
    )

    run = _create_queued_run(
        session,
        account_id=account_id,
        created_by_user_id=created_by_user_id,
        assembly_version=assembly_version,
        tune_id=tune_id,
        load_case_id=load_case_id,
        execution_preset_id=execution_preset_id,
        input_contract=document,
        contract_hash=contract_hash,
        cinder_model_version=cinder_model_version,
        contract_schema_version=contract_schema_version,
    )
    _mark_running(run)
    session.flush()

    try:
        result = gateway.run_simulation(
            document,
            include_reported_segments=include_reported_segments,
            include_raw_trace=include_raw_trace,
        )
    except Exception as exc:  # keep the DB run as a durable failed record.
        _mark_failed(run, message=str(exc), code=type(exc).__name__)
        session.flush()
        return SubmittedLibraryRun(run=run, cache_hit=False)

    full_result_artifact = _create_inline_result_artifact(
        run_id=run.id,
        cache_entry_id=None,
        result=result,
    )
    session.add(full_result_artifact)
    session.flush()

    preview = _preview_series(result, source_result_hash=full_result_artifact.content_hash)
    if existing_cache_entry is None:
        cache_entry = RunCacheEntry(
            contract_hash=contract_hash,
            cinder_model_version=cinder_model_version,
            contract_schema_version=contract_schema_version,
            status="completed",
            full_result_artifact_id=full_result_artifact.id,
            summary_scalars=_summary_scalars(result),
            summary_series=preview,
        )
        session.add(cache_entry)
        session.flush()
    else:
        cache_entry = existing_cache_entry
        cache_entry.status = "completed"
        cache_entry.full_result_artifact_id = full_result_artifact.id
        cache_entry.summary_scalars = _summary_scalars(result)
        cache_entry.summary_series = preview
        cache_entry.last_accessed_at = utc_now()
        session.flush()

    full_result_artifact.cache_entry_id = cache_entry.id
    preview_artifact = _create_inline_preview_artifact(
        run_id=run.id,
        cache_entry_id=cache_entry.id,
        preview=preview,
    )
    session.add(preview_artifact)
    session.flush()

    _mark_completed(run, result=result, cache_entry=cache_entry, preview=preview)
    session.flush()
    return SubmittedLibraryRun(run=run, cache_hit=False)


def submit_rerun_from_database_run(
    session: Session,
    *,
    gateway: CinderGateway,
    source_run_id: str,
    created_by_user_id: str | None = None,
    include_reported_segments: bool = False,
    include_raw_trace: bool = False,
) -> SubmittedLibraryRun:
    """Rerun a persisted library run from its frozen stored input contract.

    This is the product-facing rerun path for old runs whose full-result
    artifact may have been evicted. It does not re-resolve live library
    objects, so archived/deprecated/changed source objects cannot alter the
    rerun. The new run keeps the same frozen executable contract and records a
    fresh persisted run row.
    """

    source_run = get_database_run(session, source_run_id)
    document = copy.deepcopy(source_run.input_contract)
    contract_hash = source_run.contract_hash or canonical_json_hash(executable_contract(document))
    document["contract_hash"] = contract_hash
    cinder_model_version = source_run.cinder_model_version or str(CINDER_MODEL_VERSION)
    contract_schema_version = int(
        source_run.contract_schema_version or document.get("schema_version", 1)
    )

    validation = gateway.validate_simulation_case(document)
    if not bool(validation.get("is_valid")):
        raise ApiProblem(
            422,
            "simulation_case_invalid",
            "The stored simulation input failed CINDER validation.",
            {"validation": validation},
        )

    cached = _completed_cache_entry(
        session,
        contract_hash=contract_hash,
        cinder_model_version=cinder_model_version,
        contract_schema_version=contract_schema_version,
    )
    if cached is not None:
        run = _create_completed_cache_hit_run_from_source(
            session,
            source_run=source_run,
            created_by_user_id=created_by_user_id,
            input_contract=document,
            contract_hash=contract_hash,
            cinder_model_version=cinder_model_version,
            contract_schema_version=contract_schema_version,
            cache_entry=cached,
        )
        return SubmittedLibraryRun(run=run, cache_hit=True)

    existing_cache_entry = _cache_entry_by_contract(
        session,
        contract_hash=contract_hash,
        cinder_model_version=cinder_model_version,
        contract_schema_version=contract_schema_version,
    )

    run = _create_queued_run_from_source(
        session,
        source_run=source_run,
        created_by_user_id=created_by_user_id,
        input_contract=document,
        contract_hash=contract_hash,
        cinder_model_version=cinder_model_version,
        contract_schema_version=contract_schema_version,
    )
    _mark_running(run)
    session.flush()

    try:
        result = gateway.run_simulation(
            document,
            include_reported_segments=include_reported_segments,
            include_raw_trace=include_raw_trace,
        )
    except Exception as exc:  # keep the DB run as a durable failed record.
        _mark_failed(run, message=str(exc), code=type(exc).__name__)
        session.flush()
        return SubmittedLibraryRun(run=run, cache_hit=False)

    full_result_artifact = _create_inline_result_artifact(
        run_id=run.id,
        cache_entry_id=None,
        result=result,
    )
    session.add(full_result_artifact)
    session.flush()

    preview = _preview_series(result, source_result_hash=full_result_artifact.content_hash)
    if existing_cache_entry is None:
        cache_entry = RunCacheEntry(
            contract_hash=contract_hash,
            cinder_model_version=cinder_model_version,
            contract_schema_version=contract_schema_version,
            status="completed",
            full_result_artifact_id=full_result_artifact.id,
            summary_scalars=_summary_scalars(result),
            summary_series=preview,
        )
        session.add(cache_entry)
        session.flush()
    else:
        cache_entry = existing_cache_entry
        cache_entry.status = "completed"
        cache_entry.full_result_artifact_id = full_result_artifact.id
        cache_entry.summary_scalars = _summary_scalars(result)
        cache_entry.summary_series = preview
        cache_entry.last_accessed_at = utc_now()
        session.flush()

    full_result_artifact.cache_entry_id = cache_entry.id
    preview_artifact = _create_inline_preview_artifact(
        run_id=run.id,
        cache_entry_id=cache_entry.id,
        preview=preview,
    )
    session.add(preview_artifact)
    session.flush()

    _mark_completed(run, result=result, cache_entry=cache_entry, preview=preview)
    session.flush()
    return SubmittedLibraryRun(run=run, cache_hit=False)


def get_database_run(session: Session, run_id: str) -> Run:
    run = session.get(Run, run_id)
    if run is None:
        raise RunNotFoundError(run_id)
    return run


def get_database_run_result(session: Session, run_id: str) -> JsonDict:
    run = get_database_run(session, run_id)
    if run.status != "completed":
        raise ApiProblem(
            409,
            "run_result_not_available",
            f"Run {run_id!r} is {run.status}; a result is not available yet.",
            {"status": run.status},
        )
    artifact = _result_artifact_for_run(session, run)
    if artifact is None or artifact.inline_payload is None:
        raise ApiProblem(
            410,
            "run_result_artifact_missing",
            f"Run {run_id!r} completed but its full result artifact is unavailable.",
            {"run_id": run_id, "cache_entry_id": run.cache_entry_id},
        )
    return copy.deepcopy(artifact.inline_payload)


def get_database_run_input_contract(session: Session, run_id: str) -> JsonDict:
    """Return the frozen input contract for rerunning a persisted library run."""

    run = get_database_run(session, run_id)
    return copy.deepcopy(run.input_contract)


def get_database_run_preview(session: Session, run_id: str) -> JsonDict:
    """Return the durable preview payload for a completed persisted run."""

    run = get_database_run(session, run_id)
    if run.status != "completed":
        raise ApiProblem(
            409,
            "run_preview_not_available",
            f"Run {run_id!r} is {run.status}; a preview is not available yet.",
            {"status": run.status},
        )
    artifact = _preview_artifact_for_run(session, run)
    if artifact is not None and artifact.inline_payload is not None:
        return copy.deepcopy(artifact.inline_payload)
    if run.summary_series:
        return copy.deepcopy(run.summary_series)
    raise ApiProblem(
        410,
        "run_preview_missing",
        f"Run {run_id!r} completed but its preview payload is unavailable.",
        {"run_id": run_id, "cache_entry_id": run.cache_entry_id},
    )


def build_preview_from_result(result: JsonDict) -> JsonDict:
    """Build the current default preview from an in-memory direct-run result."""

    result_hash = canonical_json_hash(result)
    return _preview_series(result, source_result_hash=result_hash)


def list_database_runs(
    session: Session,
    *,
    account_id: str | None = None,
    vehicle_assembly_version_id: str | None = None,
    limit: int = 50,
) -> list[Run]:
    stmt = select(Run)
    if account_id is not None:
        stmt = stmt.where(Run.account_id == account_id)
    if vehicle_assembly_version_id is not None:
        stmt = stmt.where(Run.vehicle_assembly_version_id == vehicle_assembly_version_id)
    stmt = stmt.order_by(Run.submitted_at.desc()).limit(limit)
    return list(session.scalars(stmt).all())


def executable_contract(document: JsonDict) -> JsonDict:
    """Return the pure CINDER-executable subset used for run cache hashing."""

    return {
        key: copy.deepcopy(document[key]) for key in EXECUTABLE_DOCUMENT_KEYS if key in document
    }


def _completed_cache_entry(
    session: Session,
    *,
    contract_hash: str,
    cinder_model_version: str,
    contract_schema_version: int,
) -> RunCacheEntry | None:
    stmt = select(RunCacheEntry).where(
        RunCacheEntry.contract_hash == contract_hash,
        RunCacheEntry.cinder_model_version == cinder_model_version,
        RunCacheEntry.contract_schema_version == contract_schema_version,
        RunCacheEntry.status == "completed",
    )
    cache_entry = session.scalar(stmt)
    if cache_entry is None:
        return None
    artifact = None
    if cache_entry.full_result_artifact_id is not None:
        artifact = session.get(RunArtifact, cache_entry.full_result_artifact_id)
    if artifact is None or artifact.inline_payload is None:
        return None
    cache_entry.last_accessed_at = utc_now()
    return cache_entry


def _cache_entry_by_contract(
    session: Session,
    *,
    contract_hash: str,
    cinder_model_version: str,
    contract_schema_version: int,
) -> RunCacheEntry | None:
    stmt = select(RunCacheEntry).where(
        RunCacheEntry.contract_hash == contract_hash,
        RunCacheEntry.cinder_model_version == cinder_model_version,
        RunCacheEntry.contract_schema_version == contract_schema_version,
    )
    return session.scalar(stmt)


def _create_queued_run(
    session: Session,
    *,
    account_id: str,
    created_by_user_id: str | None,
    assembly_version: VehicleAssemblyVersion,
    tune_id: str | None,
    load_case_id: str | None,
    execution_preset_id: str | None,
    input_contract: JsonDict,
    contract_hash: str,
    cinder_model_version: str,
    contract_schema_version: int,
) -> Run:
    resolution = input_contract.get("database_resolution", {})
    run = Run(
        account_id=account_id,
        created_by_user_id=created_by_user_id,
        vehicle_assembly_version_id=assembly_version.id,
        engine_version_id=assembly_version.engine_version_id,
        cvt_design_version_id=assembly_version.cvt_design_version_id,
        output_system_version_id=assembly_version.output_system_version_id,
        tune_id=tune_id,
        load_case_id=load_case_id,
        execution_preset_id=execution_preset_id,
        tune_snapshot=copy.deepcopy(resolution.get("tune_snapshot", {})),
        load_case_snapshot=copy.deepcopy(resolution.get("load_case_snapshot", {})),
        execution_snapshot=copy.deepcopy(resolution.get("execution_snapshot", {})),
        input_contract=copy.deepcopy(input_contract),
        contract_hash=contract_hash,
        cinder_model_version=cinder_model_version,
        contract_schema_version=contract_schema_version,
        status="queued",
    )
    session.add(run)
    session.flush()
    return run


def _create_queued_run_from_source(
    session: Session,
    *,
    source_run: Run,
    created_by_user_id: str | None,
    input_contract: JsonDict,
    contract_hash: str,
    cinder_model_version: str,
    contract_schema_version: int,
) -> Run:
    run = Run(
        account_id=source_run.account_id,
        created_by_user_id=created_by_user_id or source_run.created_by_user_id,
        vehicle_assembly_version_id=source_run.vehicle_assembly_version_id,
        engine_version_id=source_run.engine_version_id,
        cvt_design_version_id=source_run.cvt_design_version_id,
        output_system_version_id=source_run.output_system_version_id,
        tune_id=source_run.tune_id,
        load_case_id=source_run.load_case_id,
        execution_preset_id=source_run.execution_preset_id,
        tune_snapshot=copy.deepcopy(source_run.tune_snapshot or {}),
        load_case_snapshot=copy.deepcopy(source_run.load_case_snapshot or {}),
        execution_snapshot=copy.deepcopy(source_run.execution_snapshot or {}),
        input_contract=copy.deepcopy(input_contract),
        contract_hash=contract_hash,
        cinder_model_version=cinder_model_version,
        contract_schema_version=contract_schema_version,
        status="queued",
    )
    session.add(run)
    session.flush()
    return run


def _create_completed_cache_hit_run_from_source(
    session: Session,
    *,
    source_run: Run,
    created_by_user_id: str | None,
    input_contract: JsonDict,
    contract_hash: str,
    cinder_model_version: str,
    contract_schema_version: int,
    cache_entry: RunCacheEntry,
) -> Run:
    run = _create_queued_run_from_source(
        session,
        source_run=source_run,
        created_by_user_id=created_by_user_id,
        input_contract=input_contract,
        contract_hash=contract_hash,
        cinder_model_version=cinder_model_version,
        contract_schema_version=contract_schema_version,
    )
    cache_artifact = session.get(RunArtifact, cache_entry.full_result_artifact_id)
    if cache_artifact is None or cache_artifact.inline_payload is None:
        raise RuntimeError("Completed cache entry does not have an inline result artifact.")
    artifact = _create_inline_result_artifact(
        run_id=run.id,
        cache_entry_id=cache_entry.id,
        result=cache_artifact.inline_payload,
    )
    session.add(artifact)
    preview = copy.deepcopy(cache_entry.summary_series or {})
    session.add(
        _create_inline_preview_artifact(
            run_id=run.id,
            cache_entry_id=cache_entry.id,
            preview=preview,
        )
    )
    run.status = "completed"
    run.started_at = utc_now()
    run.completed_at = utc_now()
    run.summary_scalars = copy.deepcopy(cache_entry.summary_scalars)
    run.summary_series = preview
    run.cache_entry_id = cache_entry.id
    session.flush()
    return run


def _create_completed_cache_hit_run(
    session: Session,
    *,
    account_id: str,
    created_by_user_id: str | None,
    assembly_version: VehicleAssemblyVersion,
    tune_id: str | None,
    load_case_id: str | None,
    execution_preset_id: str | None,
    input_contract: JsonDict,
    contract_hash: str,
    cinder_model_version: str,
    contract_schema_version: int,
    cache_entry: RunCacheEntry,
) -> Run:
    run = _create_queued_run(
        session,
        account_id=account_id,
        created_by_user_id=created_by_user_id,
        assembly_version=assembly_version,
        tune_id=tune_id,
        load_case_id=load_case_id,
        execution_preset_id=execution_preset_id,
        input_contract=input_contract,
        contract_hash=contract_hash,
        cinder_model_version=cinder_model_version,
        contract_schema_version=contract_schema_version,
    )
    cache_artifact = session.get(RunArtifact, cache_entry.full_result_artifact_id)
    if cache_artifact is None or cache_artifact.inline_payload is None:
        raise RuntimeError("Completed cache entry does not have an inline result artifact.")
    artifact = _create_inline_result_artifact(
        run_id=run.id,
        cache_entry_id=cache_entry.id,
        result=cache_artifact.inline_payload,
    )
    session.add(artifact)
    preview = copy.deepcopy(cache_entry.summary_series or {})
    session.add(
        _create_inline_preview_artifact(
            run_id=run.id,
            cache_entry_id=cache_entry.id,
            preview=preview,
        )
    )
    run.status = "completed"
    run.started_at = utc_now()
    run.completed_at = utc_now()
    run.summary_scalars = copy.deepcopy(cache_entry.summary_scalars)
    run.summary_series = preview
    run.cache_entry_id = cache_entry.id
    session.flush()
    return run


def _create_inline_result_artifact(
    *,
    run_id: str,
    cache_entry_id: str | None,
    result: JsonDict,
) -> RunArtifact:
    result_snapshot = copy.deepcopy(result)
    content_hash = canonical_json_hash(result_snapshot)
    return RunArtifact(
        run_id=run_id,
        cache_entry_id=cache_entry_id,
        artifact_kind="full_result",
        storage_backend="inline_json",
        storage_key=f"runs/{run_id}/result.json",
        byte_size=_json_byte_size(result_snapshot),
        content_hash=content_hash,
        inline_payload=result_snapshot,
        evictable=True,
    )


def _create_inline_preview_artifact(
    *,
    run_id: str,
    cache_entry_id: str | None,
    preview: JsonDict,
) -> RunArtifact:
    preview_snapshot = copy.deepcopy(preview)
    content_hash = canonical_json_hash(preview_snapshot)
    return RunArtifact(
        run_id=run_id,
        cache_entry_id=cache_entry_id,
        artifact_kind="preview_series",
        storage_backend="inline_json",
        storage_key=(
            f"runs/{run_id}/previews/"
            f"{preview_snapshot.get('profile_name', DEFAULT_PREVIEW_PROFILE.name)}-"
            f"v{preview_snapshot.get('profile_version', DEFAULT_PREVIEW_PROFILE.version)}.json"
        ),
        byte_size=_json_byte_size(preview_snapshot),
        content_hash=content_hash,
        inline_payload=preview_snapshot,
        evictable=False,
    )


def _result_artifact_for_run(session: Session, run: Run) -> RunArtifact | None:
    stmt = select(RunArtifact).where(
        RunArtifact.run_id == run.id,
        RunArtifact.artifact_kind == "full_result",
    )
    artifact = session.scalar(stmt)
    if artifact is not None:
        return artifact
    if run.cache_entry_id is not None:
        cache_entry = session.get(RunCacheEntry, run.cache_entry_id)
        if cache_entry is not None and cache_entry.full_result_artifact_id is not None:
            return session.get(RunArtifact, cache_entry.full_result_artifact_id)
    return None


def _preview_artifact_for_run(session: Session, run: Run) -> RunArtifact | None:
    stmt = (
        select(RunArtifact)
        .where(
            RunArtifact.run_id == run.id,
            RunArtifact.artifact_kind == "preview_series",
        )
        .order_by(RunArtifact.created_at.desc())
    )
    artifact = session.scalar(stmt)
    if artifact is not None:
        return artifact
    if run.cache_entry_id is not None:
        stmt = (
            select(RunArtifact)
            .where(
                RunArtifact.cache_entry_id == run.cache_entry_id,
                RunArtifact.artifact_kind == "preview_series",
            )
            .order_by(RunArtifact.created_at.desc())
        )
        return session.scalar(stmt)
    return None


def _json_byte_size(payload: JsonDict) -> int:
    """Return the serialized UTF-8 size for an inline JSON artifact."""

    return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _resolution_error_status(message: str) -> int:
    """Map resolver failures to stable API status codes."""

    return 404 if message.startswith("Unknown ") else 400


def _mark_running(run: Run) -> None:
    run.status = "running"
    run.started_at = utc_now()


def _mark_completed(
    run: Run,
    *,
    result: JsonDict,
    cache_entry: RunCacheEntry,
    preview: JsonDict,
) -> None:
    run.status = "completed"
    run.completed_at = utc_now()
    run.error = None
    run.summary_scalars = _summary_scalars(result)
    run.summary_series = copy.deepcopy(preview)
    run.cache_entry_id = cache_entry.id


def _mark_failed(run: Run, *, message: str, code: str) -> None:
    run.status = "failed"
    run.completed_at = utc_now()
    run.error = {"code": code, "message": message}


def _summary_scalars(result: JsonDict) -> JsonDict:
    return {
        "metrics": copy.deepcopy(result.get("metrics", {})),
        "summary": copy.deepcopy(result.get("summary", {})),
        "warnings": copy.deepcopy(result.get("warnings", [])),
        "transitions": copy.deepcopy(result.get("transitions", [])),
    }


def _summary_series(result: JsonDict) -> JsonDict:
    """Return the current default durable preview payload."""

    return _preview_series(result)


def _preview_series(result: JsonDict, *, source_result_hash: str | None = None) -> JsonDict:
    return build_run_preview(
        result,
        profile=DEFAULT_PREVIEW_PROFILE,
        source_result_hash=source_result_hash,
    )
