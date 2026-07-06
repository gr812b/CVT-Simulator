"""FastAPI dependencies that expose composed application services."""

from __future__ import annotations

from fastapi import Request

from app.application.container import ApplicationContainer


def get_container(request: Request) -> ApplicationContainer:
    return request.app.state.container
