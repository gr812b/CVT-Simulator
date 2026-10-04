"""Database-backed fixed-window limits shared by API workers."""

import time
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import delete

from app.application.auth import digest
from app.core.errors import ApiProblem
from app.database.auth_models import AuthRateLimit


def throttle(
    request: Request, action: str, identifier: str, *, limit: int, seconds: int
) -> None:
    now = time.time()
    window = int(now // seconds)
    key = digest(f"{action}:{identifier}:{window}")
    expires = datetime.fromtimestamp((window + 1) * seconds, timezone.utc)
    # Commit independently so rejected authentication does not roll back the limit.
    with request.app.state.database_session_factory.begin() as session:
        if session.bind.dialect.name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert
        else:
            from sqlalchemy.dialects.postgresql import insert
        statement = insert(AuthRateLimit).values(key=key, count=1, expires_at=expires)
        statement = statement.on_conflict_do_update(
            index_elements=[AuthRateLimit.key], set_={"count": AuthRateLimit.count + 1}
        ).returning(AuthRateLimit.count)
        count = session.scalar(statement)
        session.execute(
            delete(AuthRateLimit).where(
                AuthRateLimit.expires_at
                < datetime.fromtimestamp(now - 3600, timezone.utc)
            )
        )
    if count > limit:
        raise ApiProblem(
            429,
            "auth_rate_limited",
            "Too many attempts. Please try again later.",
            {"retry_after_seconds": max(1, int(expires.timestamp() - now))},
        )


def throttle_ip(request: Request, action: str, *, limit: int = 40) -> None:
    address = request.client.host if request.client else "unknown"
    throttle(request, f"{action}:ip", address, limit=limit, seconds=900)
