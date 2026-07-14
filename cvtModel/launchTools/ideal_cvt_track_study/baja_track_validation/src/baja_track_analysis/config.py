from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any
import tomllib

from .gps_core import AnalysisConfig


@dataclass
class MetricConfig:
    """Spatial windows and quality rules for event metrics."""

    spatial_step_m: float = 1.0
    approach_distance_m: float = 30.0
    approach_gap_m: float = 10.0
    immediate_entry_window_m: float = 5.0
    end_speed_window_m: float = 2.0
    post_event_gap_m: float = 5.0
    post_event_window_m: float = 15.0
    recovery_fraction: float = 0.98
    recovery_limit_m: float = 60.0
    minimum_raw_samples_in_event: int = 2
    minimum_raw_samples_approach_through_end: int = 3
    grouping_recovery_fraction_threshold: float = 0.50
    grouping_resolution_multiplier: float = 1.0
    full_throttle_threshold_pct: float = 80.0
    brake_active_threshold: float = 0.5
    wheel_slip_ratio_threshold: float = 0.15
    power_band_min_rpm: float | None = None
    power_band_max_rpm: float | None = None

    def validate(self) -> None:
        positive = (
            "spatial_step_m",
            "approach_distance_m",
            "immediate_entry_window_m",
            "end_speed_window_m",
            "post_event_window_m",
            "recovery_limit_m",
        )
        for name in positive:
            if getattr(self, name) <= 0:
                raise ValueError(f"metric.{name} must be positive")
        if not 0 < self.recovery_fraction <= 1:
            raise ValueError("metric.recovery_fraction must be in (0, 1]")
        if self.approach_gap_m >= self.approach_distance_m:
            raise ValueError("metric.approach_gap_m must be smaller than approach_distance_m")
        if not 0 <= self.full_throttle_threshold_pct <= 100:
            raise ValueError("metric.full_throttle_threshold_pct must be between 0 and 100")
        if not 0 <= self.brake_active_threshold <= 1:
            raise ValueError("metric.brake_active_threshold must be between 0 and 1")
        if self.wheel_slip_ratio_threshold < 0:
            raise ValueError("metric.wheel_slip_ratio_threshold must be non-negative")
        if (self.power_band_min_rpm is None) != (self.power_band_max_rpm is None):
            raise ValueError("set both power_band_min_rpm and power_band_max_rpm, or neither")
        if self.power_band_min_rpm is not None and self.power_band_min_rpm >= self.power_band_max_rpm:
            raise ValueError("power_band_min_rpm must be smaller than power_band_max_rpm")


@dataclass
class SignatureConfig:
    """Uniform anchor-window and track-relative classification rules."""

    local_half_window_m: float = 5.0
    interpolation_step_m: float = 1.0
    baseline_step_m: float = 5.0
    slowdown_event_threshold_kmh: float = 1.0
    strong_track_percentile: float = 75.0
    strong_lap_fraction: float = 0.70
    moderate_track_percentile: float = 50.0
    moderate_lap_fraction: float = 0.50
    minimum_valid_laps: int = 6

    def validate(self) -> None:
        for name in ("local_half_window_m", "interpolation_step_m", "baseline_step_m"):
            if getattr(self, name) <= 0:
                raise ValueError(f"signature.{name} must be positive")
        for name in ("strong_track_percentile", "moderate_track_percentile"):
            if not 0 <= getattr(self, name) <= 100:
                raise ValueError(f"signature.{name} must be between 0 and 100")
        for name in ("strong_lap_fraction", "moderate_lap_fraction"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"signature.{name} must be between 0 and 1")
        if self.slowdown_event_threshold_kmh < 0:
            raise ValueError("signature.slowdown_event_threshold_kmh must be non-negative")
        if self.strong_track_percentile < self.moderate_track_percentile:
            raise ValueError("strong_track_percentile must be at least moderate_track_percentile")
        if self.strong_lap_fraction < self.moderate_lap_fraction:
            raise ValueError("strong_lap_fraction must be at least moderate_lap_fraction")
        if self.minimum_valid_laps < 1:
            raise ValueError("signature.minimum_valid_laps must be at least 1")


@dataclass
class PipelineConfig:
    gps: AnalysisConfig = field(default_factory=AnalysisConfig)
    metric: MetricConfig = field(default_factory=MetricConfig)
    signature: SignatureConfig = field(default_factory=SignatureConfig)
    write_excel: bool = True
    write_plots: bool = True

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if self.gps.profile_spacing_m <= 0 or self.gps.centreline_spacing_m <= 0:
            raise ValueError("GPS spatial spacings must be positive")
        self.metric.validate()
        self.signature.validate()

    @classmethod
    def from_toml(cls, path: Path | None) -> "PipelineConfig":
        if path is None:
            return cls()
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        gps_values = _known_values(AnalysisConfig, data.get("gps", {}), "gps")
        metric_values = _known_values(MetricConfig, data.get("metric", {}), "metric")
        signature_values = _known_values(SignatureConfig, data.get("signature", {}), "signature")
        output = data.get("output", {})
        unknown_output = set(output) - {"write_excel", "write_plots"}
        if unknown_output:
            raise ValueError(f"Unknown output config keys: {sorted(unknown_output)}")
        return cls(
            gps=AnalysisConfig(**gps_values),
            metric=MetricConfig(**metric_values),
            signature=SignatureConfig(**signature_values),
            write_excel=bool(output.get("write_excel", True)),
            write_plots=bool(output.get("write_plots", True)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "gps": asdict(self.gps),
            "metric": asdict(self.metric),
            "signature": asdict(self.signature),
            "output": {"write_excel": self.write_excel, "write_plots": self.write_plots},
        }


def _known_values(cls: type, values: dict[str, Any], section: str) -> dict[str, Any]:
    known = {field.name for field in fields(cls)}
    unknown = set(values) - known
    if unknown:
        raise ValueError(f"Unknown {section} config keys: {sorted(unknown)}")
    return dict(values)
