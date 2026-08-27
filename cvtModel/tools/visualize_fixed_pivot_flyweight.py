"""Visualize the fixed-pivot flyweight's production contact branch.

Run from ``cvtModel``:

    PYTHONPATH=src python tools/visualize_fixed_pivot_flyweight.py

The solid arm/roller is the production history-selected branch:
smallest q at fully open, then continuous branch following. Alternate
instantaneous mathematical configurations remain visible as dashed geometry.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from math import degrees, hypot
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle
from matplotlib.widgets import Slider

from cinder.model.cvt.actuation import (
    PivotedRollerContactCandidate,
    PivotedRollerFollowerGeometry,
    PivotedRollerFollowerGeometrySpec,
)
from cinder.model.cvt.profiles import (
    C3TransitionSegment,
    CircularSegment,
    LinearSegment,
    PiecewiseRamp,
)

INCH_TO_METRE = 0.0254
MILLIMETRE = 1.0e-3
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "examples" / "baja_primary_fixed_pivot_geometry.json"


@dataclass(frozen=True, slots=True)
class PreviewConfig:
    name: str
    pivot_radius: float
    arm_length: float
    roller_radius: float
    point_a_axial_offset: float
    point_a_radial_offset: float
    number_of_flyweights: int
    arm_mass_per_flyweight: float
    ramp_payload: dict[str, Any]
    ramp_axial_direction: int
    roller_side_sign: int
    axial_position_min: float
    axial_position_max: float

    @property
    def point_a_radius(self) -> float:
        return self.pivot_radius + self.point_a_radial_offset


def _inch(value: Any) -> float:
    return float(value) * INCH_TO_METRE


def _mm(value: Any) -> float:
    return float(value) * MILLIMETRE


def _segment_length(segment: dict[str, Any]) -> float:
    if "axial_span_mm" in segment:
        return _mm(segment["axial_span_mm"])
    if "axial_span_in" in segment:
        return _inch(segment["axial_span_in"])
    if "length_m" in segment:
        return float(segment["length_m"])
    raise KeyError("Ramp segment must define axial_span_mm, axial_span_in, or length_m.")


def load_config(path: Path) -> PreviewConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    m = payload["measurements"]
    ramp = payload["ramp"]
    travel = payload["local_closure_travel"]
    mass_model = payload.get("mass_model", {})

    # Backward compatibility:
    # older provisional files stored arm_mass_per_flyweight_g inside
    # "measurements"; the hardened schema stores it explicitly in
    # "mass_model" alongside the approximation assumptions.
    arm_mass_g = mass_model.get(
        "arm_mass_per_flyweight_g",
        m.get("arm_mass_per_flyweight_g"),
    )
    if arm_mass_g is None:
        raise KeyError(
            "arm_mass_per_flyweight_g must be provided either in "
            "'mass_model' (preferred) or legacy 'measurements'."
        )

    return PreviewConfig(
        name=str(payload["name"]),
        pivot_radius=_inch(m["pivot_radius_in"]),
        arm_length=_inch(m["pivot_to_roller_center_in"]),
        roller_radius=_mm(m["roller_radius_mm"]),
        point_a_axial_offset=_inch(m["point_a_from_pivot_axial_in"]),
        point_a_radial_offset=_inch(m["point_a_from_pivot_radial_in"]),
        number_of_flyweights=int(m["number_of_flyweights"]),
        arm_mass_per_flyweight=float(arm_mass_g) / 1000.0,
        ramp_payload=dict(ramp),
        ramp_axial_direction=int(ramp["ramp_axial_direction"]),
        roller_side_sign=int(ramp["roller_side_sign"]),
        axial_position_min=_inch(travel["minimum_in"]),
        axial_position_max=_inch(travel["maximum_in"]),
    )


def build_piecewise_ramp(ramp_payload: dict[str, Any]) -> PiecewiseRamp:
    """Build the physical ramp, including automatic C3 transitions."""

    if ramp_payload["kind"] != "piecewise_ramp":
        raise ValueError("Visualizer expects ramp.kind == 'piecewise_ramp'.")

    specs = list(ramp_payload["segments"])
    built: list[Any | None] = [None] * len(specs)

    for index, segment in enumerate(specs):
        kind = segment["kind"]
        if kind == "auto_c3_transition":
            continue
        length = _segment_length(segment)
        if kind == "linear_segment":
            built[index] = LinearSegment(
                length=length,
                angle_degrees=float(segment["angle_degrees"]),
            )
        elif kind == "circular_segment":
            built[index] = CircularSegment(
                length=length,
                angle_start_degrees=float(segment["angle_start_degrees"]),
                angle_end_degrees=float(segment["angle_end_degrees"]),
                quadrant=int(segment["quadrant"]),
            )
        else:
            raise ValueError(f"Unsupported ramp segment kind: {kind}")

    for index, segment in enumerate(specs):
        if segment["kind"] != "auto_c3_transition":
            continue
        if index == 0 or index == len(specs) - 1:
            raise ValueError(
                "auto_c3_transition must lie between two physical segments."
            )
        left = built[index - 1]
        right = built[index + 1]
        if left is None or right is None:
            raise ValueError("Adjacent automatic transitions are not supported.")
        built[index] = C3TransitionSegment.between_segments(
            left=left,
            right=right,
            length=_segment_length(segment),
        )

    if any(segment is None for segment in built):
        raise RuntimeError("Could not resolve all ramp segments.")
    return PiecewiseRamp(tuple(built))


def build_geometry(config: PreviewConfig) -> PivotedRollerFollowerGeometry:
    ramp = build_piecewise_ramp(config.ramp_payload)
    return PivotedRollerFollowerGeometry(
        PivotedRollerFollowerGeometrySpec(
            pivot_axial_position=0.0,
            pivot_radius=config.pivot_radius,
            arm_length=config.arm_length,
            roller_radius=config.roller_radius,
            ramp_reference_axial_position=config.point_a_axial_offset,
            ramp_reference_radius=config.point_a_radius,
            ramp_profile=ramp,
            ramp_axial_direction=config.ramp_axial_direction,
            axial_position_min=config.axial_position_min,
            axial_position_max=config.axial_position_max,
            roller_side_sign=config.roller_side_sign,
            root_scan_points=513,
            validation_positions=65,
        )
    )


def _ramp_summary_lines(ramp_payload: dict[str, Any]) -> list[str]:
    lines = []
    for index, segment in enumerate(ramp_payload["segments"], start=1):
        kind = segment["kind"]
        if "axial_span_mm" in segment:
            span_text = f'{float(segment["axial_span_mm"]):.1f} mm'
        elif "axial_span_in" in segment:
            span_text = f'{float(segment["axial_span_in"]):.4f} in'
        else:
            span_text = f'{1000.0 * float(segment["length_m"]):.1f} mm'
        if kind == "linear_segment":
            lines.append(
                f"{index}. linear {float(segment['angle_degrees']):.1f}° over {span_text}"
            )
        elif kind == "auto_c3_transition":
            lines.append(f"{index}. automatic C3 blend over {span_text}")
        elif kind == "circular_segment":
            lines.append(
                f"{index}. circular {float(segment['angle_start_degrees']):.1f}°→"
                f"{float(segment['angle_end_degrees']):.1f}° over {span_text}"
            )
        else:
            lines.append(f"{index}. {kind} over {span_text}")
    return lines


def _all_candidate_cloud(
    geometry: PivotedRollerFollowerGeometry,
    positions: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    xs: list[float] = []
    qs: list[float] = []
    for position in positions:
        for candidate in geometry.contact_candidates(float(position)):
            xs.append(float(position))
            qs.append(degrees(candidate.angle))
    return np.asarray(xs), np.asarray(qs)


def _partial_selected_trace(
    geometry: PivotedRollerFollowerGeometry,
    positions: np.ndarray,
):
    return geometry.trace_contact_branch(
        positions,
        require_complete=False,
    )


def _selected_candidate(
    geometry: PivotedRollerFollowerGeometry,
    *,
    axial_position: float,
    trace_positions: np.ndarray,
    trace_samples,
) -> PivotedRollerContactCandidate | None:
    if not trace_samples:
        return None

    usable_positions = trace_positions[: len(trace_samples)]
    if (
        axial_position < usable_positions[0]
        or axial_position > usable_positions[-1]
    ):
        return None

    reference = float(
        np.interp(
            axial_position,
            usable_positions,
            np.asarray([item.angle for item in trace_samples]),
        )
    )
    candidates = geometry.contact_candidates(axial_position)
    if not candidates:
        return None

    def distance(candidate: PivotedRollerContactCandidate) -> float:
        q = candidate.angle + 2.0 * np.pi * round(
            (reference - candidate.angle) / (2.0 * np.pi)
        )
        return abs(q - reference)

    return min(candidates, key=distance)


def create_figure(
    config: PreviewConfig,
    geometry: PivotedRollerFollowerGeometry,
    *,
    initial_position: float,
):
    positions = np.linspace(
        geometry.spec.axial_position_min,
        geometry.spec.axial_position_max,
        401,
    )
    audit = geometry.audit_operating_interval(
        sample_count=401,
        require_profile_c3=True,
    )
    trace = _partial_selected_trace(geometry, positions)
    candidate_x, candidate_q = _all_candidate_cloud(geometry, positions)

    figure = plt.figure(figsize=(13.0, 8.1))
    grid = figure.add_gridspec(
        3,
        2,
        height_ratios=(3.5, 1.45, 0.32),
        width_ratios=(3.2, 1.55),
        hspace=0.40,
        wspace=0.28,
    )
    mechanism = figure.add_subplot(grid[:2, 0])
    q_axis = figure.add_subplot(grid[0, 1])
    information = figure.add_subplot(grid[1, 1])
    slider_axis = figure.add_subplot(grid[2, :])
    information.axis("off")

    # Stable colors must be defined before any mechanism artists use them.
    branch_color = "C0"
    ramp_color = "C1"
    reference_color = "0.35"

    mechanism.set_aspect("equal", adjustable="box")
    mechanism.set_xlabel("Axial coordinate [mm]")
    mechanism.set_ylabel("Radius from shaft centre [mm]")
    mechanism.grid(True, alpha=0.18)

    ox = 0.0
    oradius = 0.0
    px = geometry.spec.pivot_axial_position / MILLIMETRE
    pr = geometry.spec.pivot_radius / MILLIMETRE
    mechanism.plot(
        [ox],
        [oradius],
        marker="o",
        linestyle="none",
        color=reference_color,
    )
    mechanism.annotate("O  shaft centre", (ox, oradius), xytext=(7, 7), textcoords="offset points", fontsize=9)
    mechanism.plot(
        [px],
        [pr],
        marker="o",
        linestyle="none",
        color=branch_color,
    )
    mechanism.annotate("P  fixed pivot", (px, pr), xytext=(7, 7), textcoords="offset points", fontsize=9)
    mechanism.plot(
        [ox, px],
        [oradius, pr],
        linestyle="--",
        linewidth=1.1,
        alpha=0.65,
        color=reference_color,
    )
    mechanism.annotate(r"$r_P$", (0.5 * (ox + px), 0.5 * (oradius + pr)), xytext=(7, 0), textcoords="offset points", fontsize=10)
    arm_circle = Circle(
        (px, pr),
        geometry.spec.arm_length / MILLIMETRE,
        fill=False,
        linestyle=":",
        linewidth=1.2,
        alpha=0.65,
        edgecolor=branch_color,
        zorder=3,
    )
    mechanism.add_patch(arm_circle)

    if candidate_x.size:
        q_axis.scatter(
            candidate_x / MILLIMETRE,
            candidate_q,
            s=8,
            alpha=0.20,
            color=branch_color,
            label="alternate mathematical contacts",
        )
    if trace:
        selected_positions = positions[: len(trace)]
        q_axis.plot(
            selected_positions / MILLIMETRE,
            np.degrees([item.angle for item in trace]),
            linewidth=2.3,
            color=branch_color,
            label="selected branch",
        )
    q_axis.set_xlabel("Local closure $x_p$ [mm]")
    q_axis.set_ylabel(r"$q_f$ [deg]")
    q_axis.grid(True, alpha=0.18)
    q_axis.legend(fontsize=8, loc="best")
    q_cursor = q_axis.axvline(
        initial_position / MILLIMETRE,
        linestyle="--",
        linewidth=1.0,
        color=reference_color,
    )

    slider = Slider(
        slider_axis,
        "local closure $x_p$ [mm]",
        geometry.spec.axial_position_min / MILLIMETRE,
        geometry.spec.axial_position_max / MILLIMETRE,
        valinit=initial_position / MILLIMETRE,
    )

    dynamic_artists: list[Any] = []
    ramp_points_x: list[float] = []
    ramp_points_r: list[float] = []
    xi_grid = np.linspace(geometry.spec.ramp_profile.x_min, geometry.spec.ramp_profile.x_max, 301)
    for position in (geometry.spec.axial_position_min, geometry.spec.axial_position_max):
        for xi in xi_grid:
            x, r = geometry.ramp_surface_point(contact_coordinate=float(xi), axial_position=float(position))
            ramp_points_x.append(x)
            ramp_points_r.append(r)

    margin = 1.12 * (geometry.spec.arm_length + geometry.spec.roller_radius)
    x_min = min(-0.15 * margin, min(ramp_points_x) - geometry.spec.roller_radius, geometry.spec.pivot_axial_position - margin)
    x_max = max(max(ramp_points_x) + geometry.spec.roller_radius, geometry.spec.pivot_axial_position + margin)
    r_min = min(-0.08 * margin, min(ramp_points_r) - geometry.spec.roller_radius)
    r_max = max(max(ramp_points_r) + geometry.spec.roller_radius, geometry.spec.pivot_radius + margin)
    mechanism.set_xlim(x_min / MILLIMETRE, x_max / MILLIMETRE)
    mechanism.set_ylim(r_min / MILLIMETRE, r_max / MILLIMETRE)

    info = information.text(0.0, 1.0, "", va="top", ha="left", transform=information.transAxes, fontsize=9)

    def clear_dynamic() -> None:
        while dynamic_artists:
            artist = dynamic_artists.pop()
            try:
                artist.remove()
            except ValueError:
                pass

    def remember(*artists: Any) -> None:
        dynamic_artists.extend(artists)

    ramp_summary_lines = _ramp_summary_lines(config.ramp_payload)

    def redraw(position: float) -> None:
        clear_dynamic()

        ramp_x: list[float] = []
        ramp_r: list[float] = []
        for xi in xi_grid:
            x, r = geometry.ramp_surface_point(contact_coordinate=float(xi), axial_position=position)
            ramp_x.append(x / MILLIMETRE)
            ramp_r.append(r / MILLIMETRE)
        ramp_line, = mechanism.plot(
            ramp_x,
            ramp_r,
            linewidth=2.1,
            color=ramp_color,
            zorder=2,
        )
        remember(ramp_line)

        ax, ar = geometry.ramp_surface_point(contact_coordinate=0.0, axial_position=position)
        a_marker, = mechanism.plot(
            [ax / MILLIMETRE],
            [ar / MILLIMETRE],
            marker="s",
            linestyle="none",
            color=ramp_color,
            zorder=4,
        )
        a_label = mechanism.annotate("A  ramp start", (ax / MILLIMETRE, ar / MILLIMETRE), xytext=(7, 7), textcoords="offset points", fontsize=9)
        remember(a_marker, a_label)

        candidates = geometry.contact_candidates(position)
        chosen = _selected_candidate(
            geometry,
            axial_position=position,
            trace_positions=positions,
            trace_samples=trace,
        )

        selected_arm_error_mm = None
        selected_arm_length_mm = None

        for candidate in candidates:
            selected = candidate == chosen
            cx = candidate.roller_center_axial_position / MILLIMETRE
            cr = candidate.roller_center_radius / MILLIMETRE

            arm, = mechanism.plot(
                [px, cx],
                [pr, cr],
                linestyle="-" if selected else "--",
                linewidth=2.6 if selected else 1.0,
                alpha=1.0 if selected else 0.28,
                color=branch_color,
                solid_capstyle="butt",
                dash_capstyle="butt",
                zorder=5 if selected else 3,
            )
            remember(arm)

            roller = Circle(
                (cx, cr),
                geometry.spec.roller_radius / MILLIMETRE,
                fill=False,
                linestyle="-" if selected else "--",
                linewidth=2.4 if selected else 1.0,
                alpha=1.0 if selected else 0.28,
                edgecolor=branch_color,
                zorder=6 if selected else 3,
            )
            mechanism.add_patch(roller)
            remember(roller)

            center_marker, = mechanism.plot(
                [cx],
                [cr],
                marker="o",
                markersize=4.5 if selected else 3.0,
                markerfacecolor="none",
                markeredgecolor=branch_color,
                linestyle="none",
                alpha=1.0 if selected else 0.28,
                zorder=7 if selected else 3,
            )
            remember(center_marker)

            contact, = mechanism.plot(
                [candidate.contact_axial_position / MILLIMETRE],
                [candidate.contact_radius / MILLIMETRE],
                marker="x",
                linestyle="none",
                color=ramp_color,
                alpha=1.0 if selected else 0.30,
                zorder=7 if selected else 3,
            )
            remember(contact)

            if selected:
                selected_arm_length_mm = hypot(cx - px, cr - pr)
                selected_arm_error_mm = (
                    selected_arm_length_mm
                    - geometry.spec.arm_length / MILLIMETRE
                )
                c_label = mechanism.annotate(
                    ("C  selected corner contact" if candidate.corner_contact else "C  selected contact"),
                    (
                        candidate.contact_axial_position / MILLIMETRE,
                        candidate.contact_radius / MILLIMETRE,
                    ),
                    xytext=(7, -13),
                    textcoords="offset points",
                    fontsize=8,
                )
                remember(c_label)

        q_cursor.set_xdata([position / MILLIMETRE, position / MILLIMETRE])

        branch_end = positions[len(trace) - 1] / MILLIMETRE if trace else float("nan")
        initial_q = degrees(trace[0].angle) if trace else float("nan")
        selected_q = degrees(chosen.angle) if chosen is not None else float("nan")

        direction_text = "toward pivot (-axial)" if geometry.spec.ramp_axial_direction == -1 else "along +axial"
        audit_status = (
            "VALID — production geometry accepted"
            if audit.is_valid
            else "INVALID — production map must reject"
        )
        finding_lines = [
            f"{item.severity.upper()}: {item.code}"
            for item in (*audit.errors[:3], *audit.warnings[:2])
        ]
        information_lines = [
            config.name,
            "",
            f"GEOMETRY AUDIT: {audit_status}",
            *finding_lines,
            "",
            f"x_p = {position / MILLIMETRE:.3f} mm",
            f"mathematical configurations = {len(candidates)}",
            (
                "selected contact type = corner"
                if chosen is not None and chosen.corner_contact
                else (
                    "selected contact type = smooth ramp"
                    if chosen is not None
                    else "selected contact type = --"
                )
            ),
            (f"selected q = {selected_q:.3f} deg" if chosen is not None else "selected q = no continuous contact here"),
            "",
            f"initial branch = smallest q = {initial_q:.3f} deg",
            f"continuous branch reaches ~{branch_end:.3f} mm",
            "",
            f"Point A / P axial = {config.point_a_axial_offset / MILLIMETRE:.3f} mm",
            f"Point A / P radial = {config.point_a_radial_offset / MILLIMETRE:.3f} mm",
            f"r_P = {config.pivot_radius / MILLIMETRE:.3f} mm",
            f"L_f = {config.arm_length / MILLIMETRE:.3f} mm",
            f"R_roll = {config.roller_radius / MILLIMETRE:.3f} mm",
            (
                f"drawn |PC| = {selected_arm_length_mm:.6f} mm"
                if selected_arm_length_mm is not None
                else "drawn |PC| = --"
            ),
            (
                f"|PC|-L_f = {selected_arm_error_mm:+.3e} mm"
                if selected_arm_error_mm is not None
                else "|PC|-L_f = --"
            ),
            (
                "audit min q' = "
                f"{audit.minimum_angle_gradient:.4g} 1/m"
                if audit.minimum_angle_gradient is not None
                else "audit min q' = --"
            ),
            (
                "audit max |q''| = "
                f"{audit.maximum_absolute_angle_curvature:.4g} 1/m²"
                if audit.maximum_absolute_angle_curvature is not None
                else "audit max |q''| = --"
            ),
            (
                "audit max arm error = "
                f"{1.0e3 * audit.maximum_arm_length_error:.3e} mm"
                if audit.maximum_arm_length_error is not None
                else "audit max arm error = --"
            ),
            "",
            "Ramp-angle convention:",
            "0 deg = axial reference line",
            "positive angle = radial motion away from shaft",
            f"positive profile coordinate runs {direction_text}",
            "Ramp segments:",
            *ramp_summary_lines,
        ]
        info.set_text("\n".join(information_lines))
        figure.canvas.draw_idle()

    slider.on_changed(lambda value_mm: redraw(float(value_mm) * MILLIMETRE))
    figure._fixed_pivot_slider = slider
    redraw(initial_position)
    figure.suptitle(
        (
            "Fixed-pivot flyweight — smallest-q branch and continuous contact"
            if audit.is_valid
            else "INVALID FIXED-PIVOT GEOMETRY — inspect audit findings"
        ),
        fontsize=14,
    )
    return figure


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--shift-mm", type=float, default=0.0)
    parser.add_argument("--save", type=Path, default=None)
    parser.add_argument("--no-show", action="store_true")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Print production geometry audit as JSON and exit nonzero if invalid.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    geometry = build_geometry(config)
    if args.validate_only:
        report = geometry.audit_operating_interval(
            sample_count=401,
            require_profile_c3=True,
        )
        print(json.dumps(report.as_dict(), indent=2))
        raise SystemExit(0 if report.is_valid else 2)

    initial = float(
        np.clip(
            args.shift_mm * MILLIMETRE,
            geometry.spec.axial_position_min,
            geometry.spec.axial_position_max,
        )
    )
    figure = create_figure(config, geometry, initial_position=initial)
    if args.save is not None:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(args.save, dpi=180, bbox_inches="tight")
        print(f"Saved {args.save}")
    if args.no_show:
        plt.close(figure)
    else:
        plt.show()


if __name__ == "__main__":
    main()
