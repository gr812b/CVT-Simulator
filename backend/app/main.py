"""FastAPI composition root for the CINDER-backed API."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import router as v1_router
from app.application.container import build_container
from app.core.errors import ApiProblem
from app.core.settings import Settings
from app.database.session import make_engine, make_session_factory
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
    app.state.settings = settings
    app.state.database_engine = make_engine(settings.database_url, echo=settings.database_echo)
    app.state.database_session_factory = make_session_factory(app.state.database_engine)

    @app.middleware("http")
    async def private_response_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(settings.api_prefix):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApiProblem)
    async def handle_api_problem(_: Request, problem: ApiProblem) -> JSONResponse:
        headers = {}
        if problem.status_code == 429 and isinstance(problem.details, dict):
            headers["Retry-After"] = str(problem.details.get("retry_after_seconds", 900))
        return JSONResponse(
            status_code=problem.status_code,
            headers=headers,
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
