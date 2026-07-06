"""Post-integration signal materialization for CINDER traces."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import TYPE_CHECKING, Mapping

import numpy as np
from numpy.typing import NDArray

from cinder.model.cvt.contact import ContactInterface, ContactTractionLaw
from cinder.model.cvt.closure import ClosureUnknowns
from cinder.execution.hybrid.cvt_regime import CVTOperatingRegime

from .inspection import CVTStateInspection, inspect_cvt_state
from .trace import CVTIntegrationTrace

if TYPE_CHECKING:
    from cinder.execution.hybrid.cvt_operating_hybrid import CVTOperatingHybridSystem


DEFAULT_REPORT_TIME_STEP_SECONDS = 0.01


@dataclass(frozen=True, slots=True)
class ReportingGrid:
    """Report-time selection independent of the solver's native trace.

    ``native`` uses every accepted solver state. Uniform modes request an
    evenly spaced global time grid and evaluate the SciPy dense solution
    retained per hybrid segment. Exact segment endpoints are always included
    so a transition remains visible as pre/post points at one timestamp.
    """

    kind: str
    count: int | None = None
    step_seconds: float | None = None

    @classmethod
    def native(cls) -> "ReportingGrid":
        return cls(kind="native")

    @classmethod
    def uniform_count(cls, count: int) -> "ReportingGrid":
        return cls(kind="uniform_count", count=count)

    @classmethod
    def uniform_time_step(cls, step_seconds: float) -> "ReportingGrid":
        return cls(kind="uniform_time_step", step_seconds=step_seconds)

    def __post_init__(self) -> None:
        if self.kind not in {"native", "uniform_count", "uniform_time_step"}:
            raise ValueError("ReportingGrid.kind must be native, uniform_count, or uniform_time_step.")
        if self.kind == "native":
            if self.count is not None or self.step_seconds is not None:
                raise ValueError("native ReportingGrid does not accept count or step_seconds.")
        elif self.kind == "uniform_count":
            if self.count is None or self.count < 2 or self.step_seconds is not None:
                raise ValueError("uniform_count ReportingGrid requires count >= 2 only.")
        else:
            if self.step_seconds is None or not isfinite(self.step_seconds) or self.step_seconds <= 0.0 or self.count is not None:
                raise ValueError("uniform_time_step ReportingGrid requires positive finite step_seconds only.")

    @property
    def requires_dense_output(self) -> bool:
        return self.kind != "native"

    def global_times(self, *, start_time: float, end_time: float) -> NDArray[np.float64]:
        if not isfinite(start_time) or not isfinite(end_time) or end_time < start_time:
            raise ValueError("Report time range must be finite and ordered.")
        if self.kind == "native":
            raise RuntimeError("native ReportingGrid has no independently requested time grid.")
        if end_time == start_time:
            return np.asarray([start_time], dtype=float)
        if self.kind == "uniform_count":
            assert self.count is not None
            return np.linspace(start_time, end_time, num=self.count, dtype=float)
        assert self.step_seconds is not None
        duration = end_time - start_time
        count = int(np.floor(duration / self.step_seconds))
        values = start_time + self.step_seconds * np.arange(count + 1, dtype=float)
        tolerance = 64.0 * np.finfo(float).eps * max(1.0, abs(start_time), abs(end_time))
        if end_time - values[-1] > tolerance:
            values = np.append(values, end_time)
        else:
            values[-1] = end_time
        return values


@dataclass(frozen=True, slots=True)
class ReportingSettings:
    """Controls for post-integration reporting.

    The high-level CINDER ``run()`` path uses a 10 ms solver-native uniform
    reporting grid by default.  This is a presentation/result convention, not
    an integration constraint: the solver still advances on its own adaptive
    mesh and the raw :class:`CVTIntegrationTrace` remains available through
    ``result.trace``.  Use :meth:`native` explicitly for an accepted-step
    report, or call ``integrate_trace()`` when no materialized report is
    desired.
    """

    grid: ReportingGrid = field(
        default_factory=lambda: ReportingGrid.uniform_time_step(
            DEFAULT_REPORT_TIME_STEP_SECONDS
        )
    )
    include_contact: bool = True
    include_actuation: bool = True
    include_closure_audit: bool = False
    include_integrated_observers: bool = True

    @classmethod
    def standard(cls) -> "ReportingSettings":
        """Return CINDER's standard 10 ms user-facing report configuration."""

        return cls()

    @classmethod
    def native(cls) -> "ReportingSettings":
        """Return an accepted-step report configuration without dense output."""

        return cls(grid=ReportingGrid.native())

    def __post_init__(self) -> None:
        if not isinstance(self.grid, ReportingGrid):
            raise TypeError("grid must be a ReportingGrid instance.")


@dataclass(frozen=True, slots=True)
class NumericSignal:
    """One frontend-neutral numeric channel aligned with a report segment."""

    key: str
    label: str
    unit: str
    group: str
    values: NDArray[np.float64]

    def __post_init__(self) -> None:
        if not self.key or not self.label or not self.unit or not self.group:
            raise ValueError("NumericSignal metadata fields must be non-empty.")
        values = np.asarray(self.values, dtype=float)
        if values.ndim != 1 or not np.all(np.isfinite(values) | np.isnan(values)):
            raise ValueError("NumericSignal.values must be a finite-or-NaN vector.")
        frozen = np.array(values, dtype=float, copy=True)
        frozen.setflags(write=False)
        object.__setattr__(self, "values", frozen)


@dataclass(frozen=True, slots=True)
class CVTReportedSegment:
    """One mode-preserving report segment with generic named channels."""

    mode: CVTOperatingRegime
    time: NDArray[np.float64]
    signals: Mapping[str, NumericSignal]

    def __post_init__(self) -> None:
        time = np.asarray(self.time, dtype=float)
        if time.ndim != 1 or time.size < 1 or not np.all(np.isfinite(time)):
            raise ValueError("CVTReportedSegment.time must be a finite non-empty vector.")
        frozen_time = np.array(time, dtype=float, copy=True)
        frozen_time.setflags(write=False)
        object.__setattr__(self, "time", frozen_time)
        signals = dict(self.signals)
        if not signals:
            raise ValueError("CVTReportedSegment requires at least one signal.")
        for key, signal in signals.items():
            if key != signal.key:
                raise ValueError("signal mapping keys must equal NumericSignal.key.")
            if signal.values.size != time.size:
                raise ValueError("every signal must align with the segment time vector.")
        object.__setattr__(self, "signals", signals)

    def signal(self, key: str) -> NumericSignal:
        """Return one named report signal or raise a descriptive key error."""

        try:
            return self.signals[key]
        except KeyError as error:
            available = ", ".join(sorted(self.signals))
            raise KeyError(
                f"Unknown report signal {key!r}; available keys: {available}."
            ) from error

    @property
    def state(self) -> NDArray[np.float64]:
        """Return the aligned six-state report matrix.

        This is a convenience view for numerical tools that need a state
        matrix while consuming a materialized report.  It is reconstructed
        solely from the standard state channels and therefore follows the
        report grid exactly.
        """

        keys = (
            "state.primary_angular_speed",
            "state.secondary_angular_speed",
            "state.belt_speed",
            "state.shift_position",
            "state.shift_speed",
            "state.secondary_shaft_angle",
        )
        matrix = np.vstack([self.signal(key).values for key in keys])
        matrix.setflags(write=False)
        return matrix

    @property
    def start_time(self) -> float:
        """Return this report segment's exact start time."""

        return float(self.time[0])

    @property
    def end_time(self) -> float:
        """Return this report segment's exact end time."""

        return float(self.time[-1])


@dataclass(frozen=True, slots=True)
class CVTResultSummary:
    duration: float
    segment_count: int
    transition_count: int
    final_state: NDArray[np.float64]

    def __post_init__(self) -> None:
        if not isfinite(self.duration) or self.duration < 0.0:
            raise ValueError("duration must be finite and non-negative.")
        values = np.asarray(self.final_state, dtype=float)
        if values.shape != (6,) or not np.all(np.isfinite(values)):
            raise ValueError("final_state must contain six finite values.")
        frozen = np.array(values, dtype=float, copy=True)
        frozen.setflags(write=False)
        object.__setattr__(self, "final_state", frozen)


@dataclass(frozen=True, slots=True)
class CVTIntegrationResult:
    """Rich report built from one raw trace, without rerunning integration.

    ``segments`` are report-grid segments.  The exact adaptive solver history
    and event/reset records remain accessible through :attr:`trace`.
    """

    trace: CVTIntegrationTrace
    segments: tuple[CVTReportedSegment, ...]
    summary: CVTResultSummary
    warnings: tuple[str, ...] = ()

    @property
    def transitions(self):
        """Return exact raw hybrid transition records."""

        return self.trace.transitions

    @property
    def completed(self) -> bool:
        """Return whether the raw hybrid integration reached its final time."""

        return self.trace.completed

    @property
    def termination_reason(self) -> str:
        return self.trace.termination_reason

    @property
    def final_time(self) -> float:
        return self.trace.final_time

    @property
    def final_state(self) -> NDArray[np.float64]:
        return self.trace.final_state


class CVTResultBuilder:
    """Materialize standard mechanics signals on a selected report-time grid."""

    def __init__(self, *, system: "CVTOperatingHybridSystem") -> None:
        self._system = system

    def build(
        self,
        trace: CVTIntegrationTrace,
        *,
        settings: ReportingSettings | None = None,
    ) -> CVTIntegrationResult:
        if not isinstance(trace, CVTIntegrationTrace):
            raise TypeError("trace must be a CVTIntegrationTrace instance.")
        # ``build(trace)`` is the low-level trace consumer, so preserve the
        # accepted solver mesh unless the caller explicitly requests a report
        # grid.  The high-level ``system.run()`` convenience path selects the
        # standard 10 ms grid instead.
        if settings is None:
            settings = ReportingSettings.native()
        if not isinstance(settings, ReportingSettings):
            raise TypeError("settings must be a ReportingSettings instance.")

        global_times = None
        if settings.grid.requires_dense_output:
            missing = [segment for segment in trace.segments if not segment.has_dense_output]
            if missing:
                raise RuntimeError(
                    "Uniform reporting requires solver-native dense output. Re-integrate "
                    "through system.run(..., reporting_settings=...), or set "
                    "HybridIntegratorSettings(retain_dense_output=True)."
                )
            global_times = settings.grid.global_times(
                start_time=trace.segments[0].start_time,
                end_time=trace.final_time,
            )

        reported: list[CVTReportedSegment] = []
        warnings: list[str] = []
        observer_offsets = (0.0, 0.0, 0.0, 0.0, 0.0)

        for raw_segment in trace.segments:
            time, state = _sample_segment(
                raw_segment,
                grid=settings.grid,
                global_times=global_times,
            )
            inspections = tuple(
                inspect_cvt_state(
                    system=self._system,
                    time=float(time[index]),
                    vector=state[:, index],
                    mode=raw_segment.mode,
                    include_closure_audit=settings.include_closure_audit,
                )
                for index in range(time.size)
            )
            signals = _build_signals(
                time=time,
                state=state,
                inspections=inspections,
                settings=settings,
                traction_law=self._system.traction_law,
                observer_offsets=observer_offsets,
            )
            if settings.include_integrated_observers:
                observer_offsets = (
                    float(signals["observer.primary_shaft_angle"].values[-1]),
                    float(signals["observer.engine_work"].values[-1]),
                    float(signals["observer.output_boundary_work"].values[-1]),
                    float(signals["observer.primary_slip_dissipation"].values[-1]),
                    float(signals["observer.secondary_slip_dissipation"].values[-1]),
                )
            if any(item.output_boundary.road_load is None for item in inspections):
                warning = "Vehicle-only road channels are NaN for at least one non-vehicle output boundary."
                if warning not in warnings:
                    warnings.append(warning)
            reported.append(
                CVTReportedSegment(
                    mode=raw_segment.mode,
                    time=time,
                    signals=signals,
                )
            )

        return CVTIntegrationResult(
            trace=trace,
            segments=tuple(reported),
            summary=CVTResultSummary(
                duration=trace.final_time - trace.segments[0].start_time,
                segment_count=len(trace.segments),
                transition_count=len(trace.transitions),
                final_state=trace.final_state,
            ),
            warnings=tuple(warnings),
        )


def _sample_segment(raw_segment, *, grid: ReportingGrid, global_times: NDArray[np.float64] | None) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    if grid.kind == "native":
        return raw_segment.time, raw_segment.state
    assert global_times is not None
    scale = max(1.0, abs(raw_segment.start_time), abs(raw_segment.end_time))
    tolerance = 128.0 * np.finfo(float).eps * scale
    mask = (global_times >= raw_segment.start_time - tolerance) & (global_times <= raw_segment.end_time + tolerance)
    requested = global_times[mask]
    time = np.unique(np.concatenate((
        np.asarray([raw_segment.start_time], dtype=float),
        requested,
        np.asarray([raw_segment.end_time], dtype=float),
    )))
    state = raw_segment.dense_state_at(time)
    return time, state

def _build_signals(
    *,
    time: NDArray[np.float64],
    state: NDArray[np.float64],
    inspections: tuple[CVTStateInspection, ...],
    settings: ReportingSettings,
    traction_law: ContactTractionLaw,
    observer_offsets: tuple[float, float, float, float, float],
) -> dict[str, NumericSignal]:
    values: dict[str, tuple[str, str, str, NDArray[np.float64]]] = {}

    def add(key: str, label: str, unit: str, group: str, data) -> None:
        values[key] = (label, unit, group, np.asarray(data, dtype=float))

    add("state.primary_angular_speed", "Primary angular speed", "rad/s", "state", state[0])
    add("state.secondary_angular_speed", "Secondary angular speed", "rad/s", "state", state[1])
    add("state.belt_speed", "Belt speed", "m/s", "state", state[2])
    add("state.shift_position", "Shift position", "m", "state", state[3])
    add("state.shift_speed", "Shift speed", "m/s", "state", state[4])
    add("state.secondary_shaft_angle", "Secondary shaft angle", "rad", "state", state[5])

    primary_radius = np.array([item.geometry.primary.effective for item in inspections])
    secondary_radius = np.array([item.geometry.secondary.effective for item in inspections])
    add("geometry.primary_effective_radius", "Primary effective radius", "m", "geometry", primary_radius)
    add("geometry.secondary_effective_radius", "Secondary effective radius", "m", "geometry", secondary_radius)
    add("geometry.primary_outer_radius", "Primary outer radius", "m", "geometry", np.array([item.geometry.primary.outer for item in inspections]))
    add("geometry.secondary_outer_radius", "Secondary outer radius", "m", "geometry", np.array([item.geometry.secondary.outer for item in inspections]))
    add("geometry.effective_ratio_secondary_over_primary", "Effective ratio r_s / r_p", "1", "geometry", secondary_radius / primary_radius)
    add("geometry.primary_wrap_angle", "Primary wrap angle", "rad", "geometry", np.array([item.geometry.primary_wrap_angle for item in inspections]))
    add("geometry.secondary_wrap_angle", "Secondary wrap angle", "rad", "geometry", np.array([item.geometry.secondary_wrap_angle for item in inspections]))

    add("boundary.engine_torque", "Input boundary torque", "N m", "boundary", np.array([item.engine_torque for item in inspections]))
    add("boundary.output_external_torque", "Output boundary torque", "N m", "boundary", np.array([item.output_boundary.external_torque for item in inspections]))
    add("boundary.output_added_inertia", "Output added inertia", "kg m^2", "boundary", np.array([item.output_boundary.added_rotational_inertia for item in inspections]))
    road = [item.output_boundary.road_load for item in inspections]
    add("vehicle.speed", "Vehicle speed", "m/s", "vehicle", np.array([np.nan if row is None else row.vehicle_speed for row in road]))
    add("vehicle.distance", "Vehicle distance", "m", "vehicle", np.array([np.nan if item.output_boundary.vehicle_distance is None else item.output_boundary.vehicle_distance for item in inspections]))
    add("vehicle.grade_angle", "Road grade", "rad", "vehicle", np.array([np.nan if row is None else row.grade_angle for row in road]))
    add("vehicle.road_force", "Road external force", "N", "vehicle", np.array([np.nan if row is None else row.external_force for row in road]))

    if settings.include_actuation:
        _add_actuation_signals(add, inspections)
    if settings.include_contact:
        _add_contact_signals(add, inspections, traction_law=traction_law)
    if settings.include_integrated_observers:
        _add_observer_signals(add, time, state, inspections, observer_offsets)
    if settings.include_closure_audit:
        _add_audit_signals(add, inspections)

    return {
        key: NumericSignal(key=key, label=label, unit=unit, group=group, values=data)
        for key, (label, unit, group, data) in values.items()
    }


def _add_actuation_signals(add, inspections: tuple[CVTStateInspection, ...]) -> None:
    for prefix, label, attr in (
        ("actuation.primary", "Primary", "primary_actuation"),
        ("actuation.secondary", "Secondary", "secondary_actuation"),
    ):
        available = [getattr(item, attr) for item in inspections]
        add(
            f"{prefix}.total_clamp_force",
            f"{label} total clamp force",
            "N",
            "actuation",
            np.array([
                np.nan if actuator is None
                else actuator.resolve_total(
                    inspection.closure_unknowns or ClosureUnknowns.zeros()
                )
                for actuator, inspection in zip(available, inspections, strict=True)
            ]),
        )
        keys = sorted({
            contribution.key
            for actuator in available if actuator is not None
            for contribution in actuator.contributions
        })
        for key in keys:
            signal_label = next(
                contribution.label
                for actuator in available if actuator is not None
                for contribution in actuator.contributions if contribution.key == key
            )
            add(
                f"{prefix}.{key}",
                f"{label} {signal_label}",
                "N",
                "actuation",
                np.array([
                    np.nan if actuator is None
                    else actuator.resolve_contributions(
                        inspection.closure_unknowns or ClosureUnknowns.zeros()
                    ).get(key, np.nan)
                    for actuator, inspection in zip(available, inspections, strict=True)
                ]),
            )


def _add_contact_signals(
    add,
    inspections: tuple[CVTStateInspection, ...],
    *,
    traction_law: ContactTractionLaw,
) -> None:
    contact = [item.contact for item in inspections]
    unknowns = [item.closure_unknowns for item in inspections]
    add("contact.primary_lambda", "Primary traction utilization", "1", "contact", np.array([np.nan if row is None else row.traction_utilization.primary_lambda for row in contact]))
    add("contact.secondary_lambda", "Secondary traction utilization", "1", "contact", np.array([np.nan if row is None else row.traction_utilization.secondary_lambda for row in contact]))
    add("contact.primary_relative_speed", "Primary relative speed", "m/s", "contact", np.array([np.nan if row is None else row.relative_motion.primary_relative_speed for row in contact]))
    add("contact.secondary_relative_speed", "Secondary relative speed", "m/s", "contact", np.array([np.nan if row is None else row.relative_motion.secondary_relative_speed for row in contact]))
    add("contact.primary_normal_resultant", "Primary normal resultant", "N", "contact", np.array([np.nan if row is None else row.normal_primary for row in contact]))
    add("contact.secondary_normal_resultant", "Secondary normal resultant", "N", "contact", np.array([np.nan if row is None else row.normal_secondary for row in contact]))
    add("contact.primary_transmitted_torque", "Primary transmitted torque", "N m", "contact", np.array([np.nan if row is None else row.primary_torque for row in unknowns]))
    add("contact.secondary_transmitted_torque", "Secondary transmitted torque", "N m", "contact", np.array([np.nan if row is None else row.secondary_torque for row in unknowns]))
    add("contact.primary_static_margin", "Primary static traction margin", "1", "contact", np.array([
        np.nan if row is None else traction_law.static_margin_at(ContactInterface.PRIMARY, row.traction_utilization.primary_lambda)
        for row in contact
    ]))
    add("contact.secondary_static_margin", "Secondary static traction margin", "1", "contact", np.array([
        np.nan if row is None else traction_law.static_margin_at(ContactInterface.SECONDARY, row.traction_utilization.secondary_lambda)
        for row in contact
    ]))


def _add_observer_signals(add, time, state, inspections, offsets) -> None:
    primary_angle, engine_work, output_work, primary_loss, secondary_loss = offsets
    primary_angle_values = primary_angle + _cumulative_trapezoid(time, state[0])
    engine_power = np.array([item.engine_torque for item in inspections]) * state[0]
    output_power = np.array([item.output_boundary.external_torque for item in inspections]) * state[1]
    primary_slip_power = np.array([
        _slip_power(item, ContactInterface.PRIMARY)
        for item in inspections
    ])
    secondary_slip_power = np.array([
        _slip_power(item, ContactInterface.SECONDARY)
        for item in inspections
    ])
    add("observer.primary_shaft_angle", "Primary shaft angle", "rad", "observer", primary_angle_values)
    add("observer.engine_work", "Engine boundary work", "J", "observer", engine_work + _cumulative_trapezoid(time, engine_power))
    add("observer.output_boundary_work", "Output boundary work", "J", "observer", output_work + _cumulative_trapezoid(time, output_power))
    add("observer.primary_slip_dissipation", "Primary contact slip dissipation", "J", "observer", primary_loss + _cumulative_trapezoid(time, primary_slip_power))
    add("observer.secondary_slip_dissipation", "Secondary contact slip dissipation", "J", "observer", secondary_loss + _cumulative_trapezoid(time, secondary_slip_power))


def _slip_power(inspection: CVTStateInspection, interface: ContactInterface) -> float:
    if inspection.contact is None or inspection.closure_unknowns is None:
        return 0.0
    if interface is ContactInterface.PRIMARY:
        torque = inspection.closure_unknowns.primary_torque
        radius = inspection.geometry.primary.effective
        speed = inspection.contact.relative_motion.primary_relative_speed
    else:
        torque = inspection.closure_unknowns.secondary_torque
        radius = inspection.geometry.secondary.effective
        speed = inspection.contact.relative_motion.secondary_relative_speed
    return abs(torque / radius * speed)


def _add_audit_signals(add, inspections: tuple[CVTStateInspection, ...]) -> None:
    audits = [item.closure_audit for item in inspections]
    add("audit.closure_condition_number", "Closure condition number", "1", "audit", np.array([np.nan if item is None else item.condition_number for item in audits]))
    add("audit.closure_matrix_rank", "Closure matrix rank", "1", "audit", np.array([np.nan if item is None else item.matrix_rank for item in audits]))
    add("audit.closure_max_abs_residual", "Closure maximum residual", "1", "audit", np.array([np.nan if item is None else item.max_abs_equation_residual for item in audits]))


def _cumulative_trapezoid(time: NDArray[np.float64], rate: NDArray[np.float64]) -> NDArray[np.float64]:
    values = np.zeros(time.size, dtype=float)
    if time.size > 1:
        values[1:] = np.cumsum(0.5 * (rate[:-1] + rate[1:]) * np.diff(time))
    return values
