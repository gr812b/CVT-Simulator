"""FastAPI dependencies that expose composed application services."""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from urllib.parse import urlsplit

from app.application.auth import Principal, csrf_token, get_principal
from app.application.container import ApplicationContainer
from app.core.errors import ApiProblem
from fastapi import Depends, Request
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session

session_cookie = APIKeyCookie(name="cinder_session", auto_error=False)


def get_container(request: Request) -> ApplicationContainer:
    return request.app.state.container


def get_database_session(request: Request) -> Iterator[Session]:
    factory = request.app.state.database_session_factory
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def require_browser_request(request: Request) -> None:
    """Reject cross-origin auth mutations and HTML form login CSRF."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    settings = request.app.state.settings
    web = urlsplit(settings.web_url)
    allowed = {*settings.cors_origins, f"{web.scheme}://{web.netloc}"}
    origin = request.headers.get("origin")
    if origin is not None and origin not in allowed:
        raise ApiProblem(403, "origin_not_allowed", "This request origin is not allowed.")
    if request.headers.get("x-cinder-client") != "web":
        raise ApiProblem(403, "client_header_required", "The CINDER client header is required.")


def get_current_principal(
    request: Request,
    token: str | None = Depends(session_cookie),
    session: Session = Depends(get_database_session),
) -> Principal:
    principal = get_principal(session, token)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_browser_request(request)
        supplied = request.headers.get("x-csrf-token", "")
        if not secrets.compare_digest(supplied, csrf_token(principal.token)):
            raise ApiProblem(403, "csrf_invalid", "Refresh this page and try again.")
    return principal


def get_writer(principal: Principal = Depends(get_current_principal)) -> Principal:
    principal.require_write()
    return principal


class PublicReader:
    """Anonymous read identity; never passed to mutation dependencies."""

    account_id = None
    user_id = None


def get_public_reader(
    token: str | None = Depends(session_cookie),
    session: Session = Depends(get_database_session),
):
    if token:
        try:
            return get_principal(session, token)
        except ApiProblem as error:
            if error.status_code != 401:
                raise
    return PublicReader()
