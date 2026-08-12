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
        database_echo = getenv("CVT_DATABASE_ECHO", "0").strip().lower() in {"1", "true", "yes"}
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
        )

    def resolved_preset_directory(self) -> Path:
        if self.preset_directory is not None:
            return self.preset_directory
        return Path(__file__).resolve().parents[2] / "presets"
