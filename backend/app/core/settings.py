"""Small application configuration surface for the Phase-2 backend."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from os import getenv
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings independent of FastAPI and CINDER internals."""

    api_prefix: str = "/api/v1"
    preset_directory: Path | None = None
    run_timeout_seconds: float = 300.0
    # Compatibility constructor option for old callers; execution is always durable.
    run_executor_mode: Literal["process", "inline"] = "process"
    run_queue_timeout_seconds: float = 3600.0
    run_recovery_grace_seconds: float = 15.0
    run_submission_limit: int = 6
    run_submission_window_seconds: int = 60
    run_max_duration_seconds: float = 300.0
    run_max_report_samples: int = 40000
    run_max_input_bytes: int = 2_000_000
    run_max_result_bytes: int = 64_000_000
    run_memory_limit_mb: int = 4096
    road_max_features: int = 64
    road_max_segments: int = 512
    road_max_distance_m: float = 100000.0
    road_max_grade_degrees: float = 60.0
    worker_poll_seconds: float = 1.0
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)
    database_url: str = "sqlite:///./cvt_simulator_dev.db"
    database_echo: bool = False
    environment: Literal["development", "production"] = "development"
    web_url: str = "http://localhost:5173"
    session_cookie_name: str = "cinder_session"
    session_lifetime_seconds: int = 604800
    reset_lifetime_seconds: int = 1800
    mail_mode: Literal["outbox", "smtp"] = "outbox"
    mail_outbox: Path = Path(".local/mail")
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "CINDER <noreply@localhost>"
    smtp_security: Literal["starttls", "tls"] = "starttls"

    @property
    def secure_cookies(self) -> bool:
        return self.environment == "production"

    def __post_init__(self) -> None:
        from urllib.parse import urlsplit

        url = urlsplit(self.web_url)
        if (
            url.scheme not in {"http", "https"}
            or not url.netloc
            or url.query
            or url.fragment
        ):
            raise ValueError("CVT_WEB_URL must be an absolute http(s) application URL.")
        if self.environment not in {"development", "production"}:
            raise ValueError("CVT_ENVIRONMENT must be development or production.")
        if self.mail_mode not in {"outbox", "smtp"}:
            raise ValueError("CVT_MAIL_MODE must be outbox or smtp.")
        if self.smtp_security not in {"starttls", "tls"}:
            raise ValueError("CVT_SMTP_SECURITY must be starttls or tls.")
        if self.session_lifetime_seconds <= 0 or self.reset_lifetime_seconds <= 0:
            raise ValueError("Authentication lifetimes must be positive.")
        for field in (
            "run_timeout_seconds",
            "run_queue_timeout_seconds",
            "run_recovery_grace_seconds",
            "run_submission_limit",
            "run_submission_window_seconds",
            "run_max_duration_seconds",
            "run_max_report_samples",
            "run_max_input_bytes",
            "run_max_result_bytes",
            "run_memory_limit_mb",
            "road_max_features",
            "road_max_segments",
            "road_max_distance_m",
            "road_max_grade_degrees",
            "worker_poll_seconds",
        ):
            value = getattr(self, field)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{field} must be finite and positive.")
        if self.road_max_grade_degrees >= 90:
            raise ValueError("road_max_grade_degrees must be below 90.")
        if self.environment == "production":
            if url.scheme != "https" or self.mail_mode != "smtp" or not self.smtp_host:
                raise ValueError(
                    "Production requires HTTPS CVT_WEB_URL and configured SMTP mail."
                )
            if "*" in self.cors_origins:
                raise ValueError("Production CORS origins must be explicit.")

    @classmethod
    def from_environment(cls) -> Settings:
        root = Path(__file__).resolve().parents[2]
        requested_mode = getenv("CVT_RUN_EXECUTOR_MODE", "process").strip().lower()
        if requested_mode not in {"process", "inline"}:
            raise ValueError("CVT_RUN_EXECUTOR_MODE must be 'process' or 'inline'.")
        timeout = float(getenv("CVT_RUN_TIMEOUT_SECONDS", "300"))
        if timeout <= 0.0:
            raise ValueError("CVT_RUN_TIMEOUT_SECONDS must be positive.")
        database_url = getenv("CVT_DATABASE_URL", "sqlite:///./cvt_simulator_dev.db")
        database_echo = getenv("CVT_DATABASE_ECHO", "0").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        origins = tuple(
            item.strip()
            for item in getenv("CVT_CORS_ORIGINS", "http://localhost:5173").split(",")
            if item.strip()
        )
        return cls(
            preset_directory=root / "presets",
            run_timeout_seconds=timeout,
            run_executor_mode=requested_mode,  # type: ignore[arg-type]
            run_queue_timeout_seconds=float(
                getenv("CVT_RUN_QUEUE_TIMEOUT_SECONDS", "3600")
            ),
            run_recovery_grace_seconds=float(
                getenv("CVT_RUN_RECOVERY_GRACE_SECONDS", "15")
            ),
            run_submission_limit=int(getenv("CVT_RUN_SUBMISSION_LIMIT", "6")),
            run_submission_window_seconds=int(
                getenv("CVT_RUN_SUBMISSION_WINDOW_SECONDS", "60")
            ),
            run_max_duration_seconds=float(
                getenv("CVT_RUN_MAX_DURATION_SECONDS", "300")
            ),
            run_max_report_samples=int(getenv("CVT_RUN_MAX_REPORT_SAMPLES", "40000")),
            run_max_input_bytes=int(getenv("CVT_RUN_MAX_INPUT_BYTES", "2000000")),
            run_max_result_bytes=int(getenv("CVT_RUN_MAX_RESULT_BYTES", "64000000")),
            run_memory_limit_mb=int(getenv("CVT_RUN_MEMORY_LIMIT_MB", "4096")),
            road_max_features=int(getenv("CVT_ROAD_MAX_FEATURES", "64")),
            road_max_segments=int(getenv("CVT_ROAD_MAX_SEGMENTS", "512")),
            road_max_distance_m=float(getenv("CVT_ROAD_MAX_DISTANCE_M", "100000")),
            road_max_grade_degrees=float(getenv("CVT_ROAD_MAX_GRADE_DEGREES", "60")),
            worker_poll_seconds=float(getenv("CVT_WORKER_POLL_SECONDS", "1")),
            cors_origins=origins,
            database_url=database_url,
            database_echo=database_echo,
            environment=getenv("CVT_ENVIRONMENT", "development"),
            web_url=getenv("CVT_WEB_URL", "http://localhost:5173").rstrip("/"),
            session_lifetime_seconds=int(
                getenv("CVT_SESSION_LIFETIME_SECONDS", "604800")
            ),
            reset_lifetime_seconds=int(getenv("CVT_RESET_LIFETIME_SECONDS", "1800")),
            mail_mode=getenv("CVT_MAIL_MODE", "outbox"),
            mail_outbox=Path(getenv("CVT_MAIL_OUTBOX", ".local/mail")),
            smtp_host=getenv("CVT_SMTP_HOST", ""),
            smtp_port=int(getenv("CVT_SMTP_PORT", "587")),
            smtp_username=getenv("CVT_SMTP_USERNAME", ""),
            smtp_password=getenv("CVT_SMTP_PASSWORD", ""),
            smtp_from=getenv("CVT_SMTP_FROM", "CINDER <noreply@localhost>"),
            smtp_security=getenv("CVT_SMTP_SECURITY", "starttls"),
        )

    def resolved_preset_directory(self) -> Path:
        if self.preset_directory is not None:
            return self.preset_directory
        return Path(__file__).resolve().parents[2] / "presets"
