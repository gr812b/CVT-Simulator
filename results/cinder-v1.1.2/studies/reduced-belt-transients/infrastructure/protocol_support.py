"""Controlled external-load programmes for the reduced-belt exploration.

These helpers change only the secondary *boundary condition*.  The CINDER CVT
plant, contact law, closure equations, hybrid state machine, and belt equations
are untouched.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, radians
from typing import Any


def smoothstep01(value: float) -> float:
    """C1 smooth step on [0, 1]."""
    u = min(1.0, max(0.0, float(value)))
    return u * u * (3.0 - 2.0 * u)


@dataclass(frozen=True, slots=True)
class SmoothGradeProgram:
    """Flat road followed by one smooth monotone grade rise and hold."""

    start_time_s: float
    rise_time_s: float
    target_grade_deg: float

    def __post_init__(self) -> None:
        for name, value in (
            ("start_time_s", self.start_time_s),
            ("rise_time_s", self.rise_time_s),
            ("target_grade_deg", self.target_grade_deg),
        ):
            if not isfinite(float(value)):
                raise ValueError(f"{name} must be finite.")
        if self.start_time_s < 0.0:
            raise ValueError("start_time_s must be non-negative.")
        if self.rise_time_s < 0.0:
            raise ValueError("rise_time_s must be non-negative.")

    @property
    def end_time_s(self) -> float:
        return self.start_time_s + self.rise_time_s

    def grade_degrees(self, time_s: float) -> float:
        t = float(time_s)
        if t < self.start_time_s:
            return 0.0
        if self.rise_time_s == 0.0 or t >= self.end_time_s:
            return float(self.target_grade_deg)
        u = (t - self.start_time_s) / self.rise_time_s
        return float(self.target_grade_deg) * smoothstep01(u)

    def grade_radians(self, time_s: float) -> float:
        return radians(self.grade_degrees(time_s))

    def phase_name(self, time_s: float) -> str:
        t = float(time_s)
        if t < self.start_time_s:
            return "pre_load"
        if self.rise_time_s > 0.0 and t < self.end_time_s:
            return "load_rise"
        return "load_hold"

    def as_dict(self) -> dict[str, float | str]:
        return {
            "kind": "smooth_time_programmed_grade",
            "start_time_s": float(self.start_time_s),
            "rise_time_s": float(self.rise_time_s),
            "target_grade_deg": float(self.target_grade_deg),
        }


def make_time_programmed_boundary(*, base_boundary: Any, program: SmoothGradeProgram) -> Any:
    """Wrap one decoded locked-final-drive boundary with a smooth grade program.

    The decoded boundary supplies the exact vehicle, final drive, road-load law,
    and reflected inertia from the frozen simulation document.  Only grade as a
    function of time is replaced.
    """
    if not hasattr(base_boundary, "road_load"):
        raise TypeError("Controlled grade study requires a road-load secondary boundary.")
    if not hasattr(base_boundary, "reflected_rotational_inertia"):
        raise TypeError("Secondary boundary must expose reflected_rotational_inertia.")

    from cinder.model.system import ShaftBoundaryValue

    class _TimeProgrammedBoundary:
        def __init__(self) -> None:
            self.road_load = base_boundary.road_load
            self.program = program

        @property
        def reflected_rotational_inertia(self) -> float:
            return float(base_boundary.reflected_rotational_inertia)

        def evaluate(self, context):
            if context.shaft != "secondary":
                raise ValueError("Time-programmed load boundary must attach to secondary.")
            secondary_angle = float(context.host["secondary_shaft_angle"])
            distance = self.road_load.final_drive.vehicle_distance_from_secondary_angle(
                secondary_shaft_angle=secondary_angle
            )
            grade_angle = self.program.grade_radians(context.time)
            road = self.road_load.evaluate(
                secondary_angular_speed=context.cvt.secondary_angular_speed,
                grade_angle=grade_angle,
            )
            return ShaftBoundaryValue(
                external_torque=road.secondary_external_torque,
                equivalent_inertia=self.reflected_rotational_inertia,
                metadata={
                    "road_load": road,
                    "vehicle_distance": distance,
                    "grade_angle": grade_angle,
                    "study_phase": self.program.phase_name(context.time),
                },
            )

    return _TimeProgrammedBoundary()


@dataclass(frozen=True, slots=True)
class SmoothOverrunProgram:
    """Transition from normal drive to a controlled downhill overrun boundary.

    Before ``start_time_s`` the decoded reference boundaries are used. During
    the transition the secondary grade is moved smoothly toward
    ``target_grade_deg`` while primary external torque is moved smoothly toward
    ``target_primary_torque_Nm``. This is a controlled power-flow experiment,
    not a claim about an actual closed-throttle engine map.
    """

    start_time_s: float
    rise_time_s: float
    target_grade_deg: float = -20.0
    target_primary_torque_Nm: float = -5.0

    def __post_init__(self) -> None:
        for name, value in (
            ("start_time_s", self.start_time_s),
            ("rise_time_s", self.rise_time_s),
            ("target_grade_deg", self.target_grade_deg),
            ("target_primary_torque_Nm", self.target_primary_torque_Nm),
        ):
            if not isfinite(float(value)):
                raise ValueError(f"{name} must be finite.")
        if self.start_time_s < 0.0 or self.rise_time_s < 0.0:
            raise ValueError("start_time_s and rise_time_s must be non-negative.")

    @property
    def end_time_s(self) -> float:
        return self.start_time_s + self.rise_time_s

    def blend(self, time_s: float) -> float:
        t = float(time_s)
        if t < self.start_time_s:
            return 0.0
        if self.rise_time_s == 0.0 or t >= self.end_time_s:
            return 1.0
        return smoothstep01((t - self.start_time_s) / self.rise_time_s)

    def grade_radians(self, time_s: float) -> float:
        return radians(self.target_grade_deg * self.blend(time_s))

    def phase_name(self, time_s: float) -> str:
        u = self.blend(time_s)
        if u <= 0.0:
            return "pre_overrun"
        if u < 1.0:
            return "overrun_transition"
        return "overrun_hold"

    def as_dict(self) -> dict[str, float | str]:
        return {
            "kind": "controlled_overrun",
            "start_time_s": float(self.start_time_s),
            "rise_time_s": float(self.rise_time_s),
            "target_grade_deg": float(self.target_grade_deg),
            "target_primary_torque_Nm": float(self.target_primary_torque_Nm),
        }


def make_overrun_boundaries(*, base_primary: Any, base_secondary: Any, program: SmoothOverrunProgram) -> tuple[Any, Any]:
    """Return primary/secondary boundary wrappers for controlled overrun.

    The wrappers preserve the exact decoded inertias and road-load model. Only
    the primary applied torque and secondary grade are time-programmed.
    """
    if not hasattr(base_secondary, "road_load"):
        raise TypeError("Overrun study requires a road-load secondary boundary.")
    if not hasattr(base_secondary, "reflected_rotational_inertia"):
        raise TypeError("Secondary boundary must expose reflected_rotational_inertia.")

    from cinder.model.system import ShaftBoundaryValue

    class _PrimaryOverrunBoundary:
        def evaluate(self, context):
            base = base_primary.evaluate(context)
            u = program.blend(context.time)
            torque = (1.0 - u) * float(base.external_torque) + u * float(program.target_primary_torque_Nm)
            metadata = dict(getattr(base, "metadata", {}) or {})
            metadata.update({
                "study_phase": program.phase_name(context.time),
                "overrun_blend": u,
                "controlled_primary_torque_Nm": torque,
            })
            return ShaftBoundaryValue(
                external_torque=torque,
                equivalent_inertia=float(base.equivalent_inertia),
                metadata=metadata,
            )

    class _SecondaryOverrunBoundary:
        def __init__(self) -> None:
            self.road_load = base_secondary.road_load

        @property
        def reflected_rotational_inertia(self) -> float:
            return float(base_secondary.reflected_rotational_inertia)

        def evaluate(self, context):
            if context.shaft != "secondary":
                raise ValueError("Controlled overrun secondary boundary must attach to secondary.")
            secondary_angle = float(context.host["secondary_shaft_angle"])
            distance = self.road_load.final_drive.vehicle_distance_from_secondary_angle(
                secondary_shaft_angle=secondary_angle
            )
            grade_angle = program.grade_radians(context.time)
            road = self.road_load.evaluate(
                secondary_angular_speed=context.cvt.secondary_angular_speed,
                grade_angle=grade_angle,
            )
            return ShaftBoundaryValue(
                external_torque=road.secondary_external_torque,
                equivalent_inertia=self.reflected_rotational_inertia,
                metadata={
                    "road_load": road,
                    "vehicle_distance": distance,
                    "grade_angle": grade_angle,
                    "study_phase": program.phase_name(context.time),
                    "overrun_blend": program.blend(context.time),
                },
            )

    return _PrimaryOverrunBoundary(), _SecondaryOverrunBoundary()


def install_global_transport_inertia_scale(scale: float):
    """Temporarily scale only the whole-belt transport inertia row.

    This is an *isolation continuation*, not a physical belt variant. It probes
    whether the small ``m_b v_b_dot`` term is structurally influential while
    leaving local wrap inertia untouched. The returned callable restores the
    original builder and must be invoked after integration.
    """
    scale = float(scale)
    if not isfinite(scale) or scale < 0.0:
        raise ValueError("transport inertia scale must be finite and non-negative")

    from cinder.model.cvt.closure import AffineClosureScalar, ClosureEquation, ClosureGains
    import cinder.model.cvt.dynamics.state_fixed_equations as state_fixed

    original = state_fixed.build_belt_transport_equation

    def scaled_builder(*, snapshot):
        return ClosureEquation(
            name="belt_transport",
            residual=AffineClosureScalar(
                gains=ClosureGains(
                    belt_acceleration=scale * snapshot.belt_transport_mass,
                    primary_torque=1.0 / snapshot.geometry.primary.effective,
                    secondary_torque=1.0 / snapshot.geometry.secondary.effective,
                ),
            ),
        )

    state_fixed.build_belt_transport_equation = scaled_builder

    def restore() -> None:
        state_fixed.build_belt_transport_equation = original

    return restore
