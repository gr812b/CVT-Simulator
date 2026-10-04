"""Small application configuration surface for the Phase-2 backend."""

from __future__ import annotations

from dataclasses import dataclass
from os import getenv
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings independent of FastAPI and CINDER internals."""

    api_prefix: str = "/api/v1"
    preset_directory: Path | None = None
    run_timeout_seconds: float = 120.0
    run_executor_mode: Literal["process", "inline"] = "process"
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
        if self.environment == "production":
            if url.scheme != "https" or self.mail_mode != "smtp" or not self.smtp_host:
                raise ValueError(
                    "Production requires HTTPS CVT_WEB_URL and configured SMTP mail."
                )
            if "*" in self.cors_origins:
                raise ValueError("Production CORS origins must be explicit.")

    @classmethod
    def from_environment(cls) -> "Settings":
        root = Path(__file__).resolve().parents[2]
        requested_mode = getenv("CVT_RUN_EXECUTOR_MODE", "process").strip().lower()
        if requested_mode not in {"process", "inline"}:
            raise ValueError("CVT_RUN_EXECUTOR_MODE must be 'process' or 'inline'.")
        timeout = float(getenv("CVT_RUN_TIMEOUT_SECONDS", "120"))
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
