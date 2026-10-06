"""Durable run artifacts, including read-only compatibility with legacy caches."""

from __future__ import annotations

import copy
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiProblem, RunNotFoundError
from app.database.hashing import canonical_json_hash
from app.database.models import Run, RunArtifact, RunCacheEntry
from app.database.run_previews import DEFAULT_PREVIEW_PROFILE, build_run_preview

JsonDict = dict[str, Any]


def get_database_run(session: Session, run_id: str) -> Run:
    run = session.get(Run, run_id)
    if run is None:
        raise RunNotFoundError(run_id)
    return run


def get_database_run_result(session: Session, run_id: str) -> JsonDict:
    run = get_database_run(session, run_id)
    artifact = _result_artifact_for_run(session, run)
    if artifact is None or artifact.inline_payload is None:
        raise ApiProblem(
            409 if run.status in {"queued", "running"} else 410,
            "run_result_artifact_missing",
            f"Run {run_id!r} has no saved result available yet.",
            {"run_id": run_id, "cache_entry_id": run.cache_entry_id},
        )
    return copy.deepcopy(artifact.inline_payload)


def get_database_run_input_contract(session: Session, run_id: str) -> JsonDict:
    """Return the frozen input contract for rerunning a persisted library run."""

    run = get_database_run(session, run_id)
    return copy.deepcopy(run.input_contract)


def get_database_run_preview(session: Session, run_id: str) -> JsonDict:
    """Return the latest durable preview, including saved partial runs."""

    run = get_database_run(session, run_id)
    artifact = _preview_artifact_for_run(session, run)
    if artifact is not None and artifact.inline_payload is not None:
        return copy.deepcopy(artifact.inline_payload)
    if run.summary_series:
        return copy.deepcopy(run.summary_series)
    raise ApiProblem(
        409 if run.status in {"queued", "running"} else 410,
        "run_preview_missing",
        f"Run {run_id!r} has no saved preview available yet.",
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


def verify_result_contract(result: JsonDict, *, expected_version: int) -> None:
    actual = result.get("contract_version")
    if actual != expected_version:
        raise RuntimeError(
            "Installed CINDER projected simulation-result contract "
            f"version {actual!r}; backend expected {expected_version}."
        )


def create_result_artifact(
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


def create_preview_artifact(
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


def summary_scalars(result: JsonDict) -> JsonDict:
    return {
        "metrics": copy.deepcopy(result.get("metrics", {})),
        "summary": copy.deepcopy(result.get("summary", {})),
        "warnings": copy.deepcopy(result.get("warnings", [])),
        "transitions": copy.deepcopy(result.get("transitions", [])),
    }


def _preview_series(result: JsonDict, *, source_result_hash: str | None = None) -> JsonDict:
    return build_run_preview(
        result,
        profile=DEFAULT_PREVIEW_PROFILE,
        source_result_hash=source_result_hash,
    )
