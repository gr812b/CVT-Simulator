"""Serialize retry-safe configuration copies and preserve their attribution."""

from sqlalchemy import select, update

from app.application import physical_library
from app.core.errors import ApiProblem
from app.database.base import utc_now
from app.database.hashing import canonical_json_hash
from app.database.models import Account
from app.database.publication_models import ConfigurationCopy
from app.schemas.results import ConfigurationCopyResult


def begin_copy(session, principal, request, source):
    principal.require_write()
    fingerprint = canonical_json_hash({"source": source, **request.model_dump()})
    session.execute(
        update(Account).where(Account.id == principal.account_id).values(updated_at=utc_now())
    )
    existing = session.scalar(
        select(ConfigurationCopy).where(
            ConfigurationCopy.account_id == principal.account_id,
            ConfigurationCopy.request_key == request.request_key,
        )
    )
    if existing and existing.request_hash != fingerprint:
        raise ApiProblem(409, "copy_request_conflict", "This request key belongs to another copy.")
    return existing, fingerprint


def copy_result(session, principal, record):
    from app.database import library

    obj = session.get(
        library.binding_for(physical_library.RESOURCES[record.kind]).object_model,
        record.object_id,
    )
    return ConfigurationCopyResult(
        item=physical_library.item_response(obj, record.kind, principal),
        scenario_id=record.scenario_id,
        source_run_id=record.run_id,
    )
