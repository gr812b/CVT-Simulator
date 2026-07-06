"""FastAPI composition root for the CINDER-backed API."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import router as v1_router
from app.application.container import build_container
from app.core.errors import ApiProblem
from app.core.settings import Settings
from app.schemas.common import HealthResponse


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = Settings.from_environment() if settings is None else settings
    app = FastAPI(
        title="CVT Simulator API",
        version="1.0.0",
        description=(
            "HTTP adapter around CINDER's public contracts. All CVT mechanics "
            "remain in CINDER; this service owns transport, runs, and presets."
        ),
    )
    app.state.container = build_container(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApiProblem)
    async def handle_api_problem(_: Request, problem: ApiProblem) -> JSONResponse:
        return JSONResponse(
            status_code=problem.status_code,
            content={
                "error": {
                    "code": problem.code,
                    "message": problem.message,
                    "details": problem.details,
                }
            },
        )

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        return HealthResponse()

    app.include_router(v1_router, prefix=settings.api_prefix)
    return app


app = create_app()
