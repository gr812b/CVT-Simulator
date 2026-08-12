from __future__ import annotations

import argparse
import csv
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import matplotlib.pyplot as plt
from matplotlib import animation
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Polygon
from matplotlib.widgets import Slider
import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class TireSlipPlaybackTrace:
    time_s: NDArray[np.float64]
    vehicle_position_m: NDArray[np.float64]
    vehicle_speed_mps: NDArray[np.float64]
    wheel_patch_speed_mps: NDArray[np.float64]
    slip_speed_mps: NDArray[np.float64]
    slip_ratio: NDArray[np.float64]
    tire_force_n: NDArray[np.float64]
    tire_utilization: NDArray[np.float64]
    grade_deg: NDArray[np.float64]
    terrain_mu: NDArray[np.float64]
    primary_rpm: NDArray[np.float64]
    secondary_rpm: NDArray[np.float64]
    shift_mm: NDArray[np.float64]
    airborne: NDArray[np.bool_]
    terrain_segment: tuple[str, ...]

    @property
    def duration_s(self) -> float:
        return float(self.time_s[-1] - self.time_s[0]) if self.time_s.size else 0.0


@dataclass(slots=True)
class _PlaybackState:
    paused: bool = False
    current_index: int = 0
    playback_speed: float = 1.0
    manual_step: int | None = None
    sim_time_s: float = 0.0
    last_wall_time_s: float = 0.0


def load_trace_csv(path: Path) -> TireSlipPlaybackTrace:
    rows = []
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        raise ValueError(f"Trace file contains no samples: {path}")

    def arr(key: str) -> NDArray[np.float64]:
        return np.asarray([float(r[key]) for r in rows], dtype=float)

    def bool_arr(key: str) -> NDArray[np.bool_]:
        if key not in rows[0]:
            return np.zeros(len(rows), dtype=bool)
        return np.asarray([str(r[key]).strip().lower() in {"1", "true", "yes", "y"} for r in rows], dtype=bool)

    return TireSlipPlaybackTrace(
        time_s=arr("time_s"),
        vehicle_position_m=arr("vehicle_position_m"),
        vehicle_speed_mps=arr("vehicle_speed_mps"),
        wheel_patch_speed_mps=arr("wheel_patch_speed_mps"),
        slip_speed_mps=arr("slip_speed_mps"),
        slip_ratio=arr("slip_ratio"),
        tire_force_n=arr("tire_force_n"),
        tire_utilization=arr("tire_utilization"),
        grade_deg=arr("grade_deg"),
        terrain_mu=arr("terrain_mu"),
        primary_rpm=arr("primary_rpm"),
        secondary_rpm=arr("secondary_rpm"),
        shift_mm=arr("shift_mm"),
        airborne=bool_arr("airborne"),
        terrain_segment=tuple(r["terrain_segment"] for r in rows),
    )


def _slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace("/", "_").replace("-", "_")


def resolve_trace_path(*, trace: Path | None, run_dir: Path, case: str | None) -> Path:
    if trace is not None:
        return trace
    if case:
        slug = _slug(case)
        candidate = run_dir / slug / f"{slug}_trace.csv"
        if candidate.exists():
            return candidate
    candidates = sorted(run_dir.glob("*/**/*_trace.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0]
    raise FileNotFoundError("Could not resolve a tire-slip trace csv. Provide --trace or --case.")


def _rotate(points: NDArray[np.float64], angle_rad: float) -> NDArray[np.float64]:
    c = float(np.cos(angle_rad))
    s = float(np.sin(angle_rad))
    rot = np.asarray([[c, -s], [s, c]], dtype=float)
    return points @ rot.T


def _wheel_spoke_segments(center_local: tuple[float, float], radius: float, angle_rad: float, *, count: int = 6) -> list[NDArray[np.float64]]:
    cx, cy = center_local
    segments: list[NDArray[np.float64]] = []
    for k in range(count):
        phi = angle_rad + 2.0 * np.pi * k / count
        segments.append(np.asarray([[cx, cy], [cx + radius * np.cos(phi), cy + radius * np.sin(phi)]], dtype=float))
    return segments


def _wheel_rim_dot(center_local: tuple[float, float], radius: float, angle_rad: float) -> tuple[float, float]:
    cx, cy = center_local
    return (cx + radius * np.cos(angle_rad), cy + radius * np.sin(angle_rad))


def _safe_ylim(values: NDArray[np.float64], *, pad_frac: float = 0.08, minimum_span: float = 1.0) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return (-minimum_span, minimum_span)
    lo = float(np.min(finite))
    hi = float(np.max(finite))
    span = max(hi - lo, minimum_span)
    pad = pad_frac * span
    return lo - pad, hi + pad


def build_playback_figure(
    trace: TireSlipPlaybackTrace,
    *,
    title: str = "Tire-slip playback",
    playback_speed: float = 1.0,
):
    state = _PlaybackState(
        paused=False,
        current_index=0,
        playback_speed=max(1.0e-3, float(playback_speed)),
        sim_time_s=float(trace.time_s[0]),
        last_wall_time_s=time.monotonic(),
    )
    _slider_update_active = False
    _rate_slider_update_active = False
    time_s = trace.time_s
    dt = float(np.median(np.diff(time_s))) if time_s.size > 1 else 0.025
    frame_count = int(trace.time_s.size)

    fig = plt.figure(figsize=(17, 9), constrained_layout=False)
    gs = fig.add_gridspec(4, 2, width_ratios=[2.25, 1.25], height_ratios=[1, 1, 1, 1], left=0.04, right=0.98, top=0.93, bottom=0.10, wspace=0.18, hspace=0.38)
    ax_scene = fig.add_subplot(gs[:, 0])
    ax_speed = fig.add_subplot(gs[0, 1])
    ax_slip_ratio = fig.add_subplot(gs[1, 1])
    ax_rpm = fig.add_subplot(gs[2, 1])
    ax_shift_curve = fig.add_subplot(gs[3, 1])
    fig.suptitle(title)

    # Scene setup.
    ax_scene.set_aspect("equal")
    ax_scene.set_xlim(-6.8, 6.8)
    ax_scene.set_ylim(-3.8, 4.8)
    ax_scene.axis("off")

    road_line = Line2D([], [], lw=3.0, color="dimgray")
    ax_scene.add_line(road_line)
    stripe_lines = [Line2D([], [], lw=5.0, color="gold", alpha=0.8) for _ in range(9)]
    for line in stripe_lines:
        ax_scene.add_line(line)

    wheel_radius = 0.55
    front_center_local = np.asarray([1.45, wheel_radius])
    rear_center_local = np.asarray([-1.45, wheel_radius])
    body_poly_local = np.asarray([
        [-2.25, 1.25], [2.25, 1.25], [2.25, 2.25], [0.95, 2.25],
        [0.25, 2.85], [-0.95, 2.85], [-1.45, 2.25], [-2.25, 2.25],
    ], dtype=float)
    roof_poly_local = np.asarray([[-0.55, 2.35], [0.35, 2.35], [0.05, 2.72], [-0.45, 2.72]], dtype=float)

    # A transparent warning panel appears when slip/utilization are high.
    slip_warning_patch = Polygon(
        np.asarray([[-6.6, -3.55], [6.6, -3.55], [6.6, 4.55], [-6.6, 4.55]], dtype=float),
        closed=True,
        facecolor="crimson",
        edgecolor="none",
        alpha=0.0,
        zorder=-5,
    )
    ax_scene.add_patch(slip_warning_patch)

    body_patch = Polygon(body_poly_local, closed=True, facecolor="#5DADE2", edgecolor="black", linewidth=2.0)
    roof_patch = Polygon(roof_poly_local, closed=True, facecolor="#D6EAF8", edgecolor="black", linewidth=1.5)
    ax_scene.add_patch(body_patch)
    ax_scene.add_patch(roof_patch)

    front_wheel = Circle(front_center_local, wheel_radius, facecolor="black", edgecolor="gray", linewidth=2)
    rear_wheel = Circle(rear_center_local, wheel_radius, facecolor="black", edgecolor="gray", linewidth=2)
    slip_ring = Circle(rear_center_local, wheel_radius * 1.18, facecolor="none", edgecolor="crimson", linewidth=0.0, alpha=0.0)
    ax_scene.add_patch(front_wheel)
    ax_scene.add_patch(rear_wheel)
    ax_scene.add_patch(slip_ring)
    front_spokes = [Line2D([], [], lw=2.2, color="white") for _ in range(6)]
    rear_spokes = [Line2D([], [], lw=2.2, color="white") for _ in range(6)]
    for line in [*front_spokes, *rear_spokes]:
        ax_scene.add_line(line)
    front_hub = Circle(front_center_local, wheel_radius * 0.17, facecolor="silver", edgecolor="white", linewidth=1.0)
    rear_hub = Circle(rear_center_local, wheel_radius * 0.17, facecolor="silver", edgecolor="white", linewidth=1.0)
    front_dot = Circle(front_center_local, wheel_radius * 0.08, facecolor="gold", edgecolor="black", linewidth=0.8)
    rear_dot = Circle(rear_center_local, wheel_radius * 0.08, facecolor="gold", edgecolor="black", linewidth=0.8)
    for patch in [front_hub, rear_hub, front_dot, rear_dot]:
        ax_scene.add_patch(patch)

    vehicle_arrow = Line2D([], [], lw=3.5, color="tab:blue", marker=">", markevery=[1])
    patch_arrow = Line2D([], [], lw=3.5, color="tab:orange", marker=">", markevery=[1])
    slip_arrow = Line2D([], [], lw=5.0, color="crimson", marker=">", markevery=[1], alpha=0.0)
    ax_scene.add_line(vehicle_arrow)
    ax_scene.add_line(patch_arrow)
    ax_scene.add_line(slip_arrow)

    tire_arrow_label = ax_scene.text(0.02, 0.94, "", transform=ax_scene.transAxes, fontsize=10, color="tab:orange", weight="bold")
    vehicle_arrow_label = ax_scene.text(0.02, 0.90, "", transform=ax_scene.transAxes, fontsize=10, color="tab:blue", weight="bold")
    slip_arrow_label = ax_scene.text(0.02, 0.86, "", transform=ax_scene.transAxes, fontsize=10, color="crimson", weight="bold")
    slip_banner = ax_scene.text(
        0.50, 0.95, "", transform=ax_scene.transAxes, fontsize=18,
        ha="center", va="top", weight="bold", color="crimson",
        bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="crimson", alpha=0.0),
    )
    airborne_banner = ax_scene.text(
        0.50, 0.88, "", transform=ax_scene.transAxes, fontsize=16,
        ha="center", va="top", weight="bold", color="purple",
        bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="purple", alpha=0.0),
    )
    shadow_patch = Circle((0.0, 0.0), 1.0, facecolor="0.2", edgecolor="none", alpha=0.0)
    ax_scene.add_patch(shadow_patch)

    skid_lines = [Line2D([], [], lw=3.0, color="crimson", alpha=0.95) for _ in range(5)]
    smoke_puffs = [Circle((0.0, 0.0), 0.1, facecolor="lightgray", edgecolor="gray", alpha=0.0) for _ in range(5)]
    for line in skid_lines:
        ax_scene.add_line(line)
    for puff in smoke_puffs:
        ax_scene.add_patch(puff)

    scene_info = ax_scene.text(
        0.02, 0.02, "", transform=ax_scene.transAxes, fontsize=10.5,
        va="bottom", family="monospace",
        bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="0.7", alpha=0.95),
    )
    ax_scene.text(
        0.98, 0.02,
        "space: pause   ←/→: step   shift+←/→: 1 s   pgup/pgdn: 5 s   home/end: ends   ↑/↓: speed   1/r: 1×   esc: close",
        transform=ax_scene.transAxes, fontsize=9, ha="right", va="bottom", color="0.3",
    )

    slider_ax = fig.add_axes([0.16, 0.025, 0.58, 0.028])
    time_slider = Slider(slider_ax, "seek time [s]", float(trace.time_s[0]), float(trace.time_s[-1]), valinit=float(trace.time_s[0]), valstep=float(dt))
    rate_slider_ax = fig.add_axes([0.82, 0.025, 0.13, 0.028])
    rate_slider = Slider(rate_slider_ax, "rate [×]", 0.05, 4.0, valinit=state.playback_speed, valstep=0.05)

    # Dashboard plots.
    ax_speed.plot(trace.time_s, trace.vehicle_speed_mps * 3.6, label="vehicle", lw=2.0, color="tab:blue")
    ax_speed.plot(trace.time_s, trace.wheel_patch_speed_mps * 3.6, label="wheel patch", lw=2.0, color="tab:orange")
    speed_cursor = ax_speed.axvline(trace.time_s[0], color="k", lw=1.3, alpha=0.75)
    speed_vehicle_marker, = ax_speed.plot([trace.time_s[0]], [trace.vehicle_speed_mps[0] * 3.6], "o", color="tab:blue")
    speed_patch_marker, = ax_speed.plot([trace.time_s[0]], [trace.wheel_patch_speed_mps[0] * 3.6], "o", color="tab:orange")
    ax_speed.set(title="Vehicle vs tire patch speed", xlabel="time [s]", ylabel="km/h")
    ax_speed.grid(True, alpha=0.25)
    ax_speed.legend(loc="upper left", fontsize=8)

    ax_slip_ratio.plot(trace.time_s, trace.slip_ratio, label="wheel slip ratio", lw=2.0, color="crimson")
    ax_slip_ratio.axhline(0.0, color="0.3", lw=1.0)
    ax_slip_ratio.axhline(0.10, color="crimson", lw=1.0, ls="--", alpha=0.5)
    ax_slip_ratio.axhline(-0.10, color="crimson", lw=1.0, ls="--", alpha=0.5)
    slip_ratio_cursor = ax_slip_ratio.axvline(trace.time_s[0], color="k", lw=1.3, alpha=0.75)
    slip_ratio_marker, = ax_slip_ratio.plot([trace.time_s[0]], [trace.slip_ratio[0]], "o", color="crimson")
    ax_slip_ratio.set(title="Wheel slip", xlabel="time [s]", ylabel="slip ratio")
    ax_slip_ratio.set_ylim(*_safe_ylim(trace.slip_ratio, minimum_span=0.4))
    ax_slip_ratio.grid(True, alpha=0.25)

    ax_rpm.plot(trace.time_s, trace.primary_rpm, label="primary", lw=2.0, color="tab:purple")
    ax_rpm.plot(trace.time_s, trace.secondary_rpm, label="secondary", lw=2.0, color="tab:green")
    rpm_cursor = ax_rpm.axvline(trace.time_s[0], color="k", lw=1.3, alpha=0.75)
    primary_marker, = ax_rpm.plot([trace.time_s[0]], [trace.primary_rpm[0]], "o", color="tab:purple")
    secondary_marker, = ax_rpm.plot([trace.time_s[0]], [trace.secondary_rpm[0]], "o", color="tab:green")
    ax_rpm.set(title="Shaft speeds", xlabel="time [s]", ylabel="rpm")
    ax_rpm.grid(True, alpha=0.25)
    ax_rpm.legend(loc="upper left", fontsize=8)

    ax_shift_curve.plot(trace.secondary_rpm, trace.primary_rpm, lw=1.8, color="0.35", alpha=0.75, label="shift path")
    shift_current, = ax_shift_curve.plot([trace.secondary_rpm[0]], [trace.primary_rpm[0]], "o", ms=8, color="tab:red", label="current")
    shift_vline = ax_shift_curve.axvline(trace.secondary_rpm[0], color="tab:green", lw=1.2, alpha=0.8)
    shift_hline = ax_shift_curve.axhline(trace.primary_rpm[0], color="tab:purple", lw=1.2, alpha=0.8)
    ax_shift_curve.set(title="Shift curve (current point + guide lines)", xlabel="secondary rpm", ylabel="primary rpm")
    ax_shift_curve.set_xlim(*_safe_ylim(trace.secondary_rpm, minimum_span=500.0))
    ax_shift_curve.set_ylim(*_safe_ylim(trace.primary_rpm, minimum_span=500.0))
    ax_shift_curve.grid(True, alpha=0.25)
    ax_shift_curve.legend(loc="upper left", fontsize=8)

    # A plausible wheel angle from patch speed; only for visual wheel rotation.
    wheel_radius_m = 0.22  # visual-only effective tire radius; smaller value makes rotation readable in real time
    theta = np.zeros_like(trace.time_s)
    if trace.time_s.size > 1:
        # Side view of a vehicle moving forward to the right should appear to rotate clockwise,
        # which corresponds to a negative mathematical angle in the plot frame.
        omega = -trace.wheel_patch_speed_mps / wheel_radius_m
        for i in range(1, trace.time_s.size):
            theta[i] = theta[i - 1] + 0.5 * (omega[i - 1] + omega[i]) * (trace.time_s[i] - trace.time_s[i - 1])

    # Draw at a high, fixed UI cadence. Playback speed is controlled by
    # simulated-time advancement from wall-clock time, not by skipping rows.
    interval_ms = 16

    def update_artists(i: int):
        state.current_index = max(0, min(frame_count - 1, int(i)))
        idx = state.current_index
        grade_rad = np.deg2rad(trace.grade_deg[idx])
        tangent = np.asarray([np.cos(grade_rad), np.sin(grade_rad)], dtype=float)
        normal = np.asarray([-np.sin(grade_rad), np.cos(grade_rad)], dtype=float)
        abs_slip = abs(float(trace.slip_ratio[idx]))
        abs_slip_speed = abs(float(trace.slip_speed_mps[idx]))
        util = float(trace.tire_utilization[idx])
        slip_level = min(1.0, max(abs_slip / 0.15, util - 0.75, abs_slip_speed / 1.5))
        airborne = bool(trace.airborne[idx])
        airborne_height = 0.0
        if airborne:
            start = idx
            while start > 0 and bool(trace.airborne[start - 1]):
                start -= 1
            end = idx
            while end < frame_count - 1 and bool(trace.airborne[end + 1]):
                end += 1
            span = max(1, end - start)
            phase_air = (idx - start) / span
            airborne_height = 0.35 + 1.15 * float(np.sin(np.pi * phase_air))

        # Road and center stripes. Stripe phase follows vehicle distance so motion is obvious.
        road_world = _rotate(np.asarray([[-8.0, 0.0], [8.0, 0.0]], dtype=float), grade_rad)
        road_line.set_data(road_world[:, 0], road_world[:, 1])
        spacing = 1.6
        phase = float(np.mod(trace.vehicle_position_m[idx], spacing))
        stripe_centers = np.linspace(-6.4, 6.4, len(stripe_lines)) - phase
        for line, center in zip(stripe_lines, stripe_centers):
            seg_world = _rotate(np.asarray([[center - 0.23, 0.0], [center + 0.23, 0.0]], dtype=float), grade_rad)
            line.set_data(seg_world[:, 0], seg_world[:, 1])

        lift_offset = airborne_height * normal
        body_patch.set_xy(_rotate(body_poly_local, grade_rad) + lift_offset)
        roof_patch.set_xy(_rotate(roof_poly_local, grade_rad) + lift_offset)
        front_wheel.center = tuple(_rotate(front_center_local.reshape(1, 2), grade_rad)[0] + lift_offset)
        rear_center_world = _rotate(rear_center_local.reshape(1, 2), grade_rad)[0] + lift_offset
        rear_wheel.center = tuple(rear_center_world)
        slip_ring.center = tuple(rear_center_world)
        shadow_center = _rotate(np.asarray([[0.0, 0.06]], dtype=float), grade_rad)[0]
        shadow_patch.center = tuple(shadow_center)
        shadow_patch.radius = 1.6 + 0.35 * airborne_height
        shadow_patch.set_alpha(0.18 if airborne else 0.0)
        slip_ring.set_edgecolor("purple" if airborne else "crimson")
        slip_ring.set_linewidth(4.0 if airborne else 1.0 + 8.0 * slip_level)
        slip_ring.set_alpha(0.80 if airborne else 0.05 + 0.85 * slip_level)

        for line, seg in zip(front_spokes, _wheel_spoke_segments(tuple(front_center_local), wheel_radius * 0.78, theta[idx], count=len(front_spokes))):
            world = _rotate(seg, grade_rad) + lift_offset
            line.set_data(world[:, 0], world[:, 1])
        for line, seg in zip(rear_spokes, _wheel_spoke_segments(tuple(rear_center_local), wheel_radius * 0.78, theta[idx], count=len(rear_spokes))):
            world = _rotate(seg, grade_rad) + lift_offset
            line.set_data(world[:, 0], world[:, 1])
        front_hub.center = tuple(_rotate(front_center_local.reshape(1, 2), grade_rad)[0] + lift_offset)
        rear_hub.center = tuple(rear_center_world)
        front_dot.center = tuple(_rotate(np.asarray([_wheel_rim_dot(tuple(front_center_local), wheel_radius * 0.78, theta[idx])]), grade_rad)[0] + lift_offset)
        rear_dot.center = tuple(_rotate(np.asarray([_wheel_rim_dot(tuple(rear_center_local), wheel_radius * 0.78, theta[idx])]), grade_rad)[0] + lift_offset)

        contact_world = _rotate(np.asarray([-1.45, 0.0], dtype=float).reshape(1, 2), grade_rad)[0]
        speed_scale = 0.085
        v_len = speed_scale * float(trace.vehicle_speed_mps[idx])
        p_len = speed_scale * float(trace.wheel_patch_speed_mps[idx])
        s_len = speed_scale * float(trace.slip_speed_mps[idx])
        veh_start = contact_world + 0.12 * normal
        veh_end = veh_start + v_len * tangent
        pat_start = contact_world + 0.44 * normal
        pat_end = pat_start + p_len * tangent
        slip_start = contact_world + 0.78 * normal
        slip_end = slip_start + s_len * tangent
        vehicle_arrow.set_data([veh_start[0], veh_end[0]], [veh_start[1], veh_end[1]])
        patch_arrow.set_data([pat_start[0], pat_end[0]], [pat_start[1], pat_end[1]])
        slip_arrow.set_data([slip_start[0], slip_end[0]], [slip_start[1], slip_end[1]])
        slip_arrow.set_alpha(0.15 + 0.85 * slip_level)

        vehicle_arrow_label.set_text(f"vehicle speed: {trace.vehicle_speed_mps[idx] * 3.6:5.1f} km/h")
        tire_arrow_label.set_text(f"patch speed:   {trace.wheel_patch_speed_mps[idx] * 3.6:5.1f} km/h")
        slip_arrow_label.set_text(f"wheel slip:    {trace.slip_ratio[idx]:+6.3f} ({trace.slip_speed_mps[idx]:+.2f} m/s)")

        if slip_level > 0.2 and not airborne:
            slip_banner.set_text("TIRE SLIP")
            slip_banner.get_bbox_patch().set_alpha(0.25 + 0.55 * slip_level)
        else:
            slip_banner.set_text("")
            slip_banner.get_bbox_patch().set_alpha(0.0)
        if airborne:
            airborne_banner.set_text("AIRBORNE — TIRE FORCE = 0")
            airborne_banner.get_bbox_patch().set_alpha(0.75)
        else:
            airborne_banner.set_text("")
            airborne_banner.get_bbox_patch().set_alpha(0.0)
        slip_warning_patch.set_alpha(0.06 if airborne else 0.10 * slip_level)

        # Skid marks and smoke puffs grow with slip level.
        if slip_level > 0.12 and not airborne:
            mark_len = 0.7 + 3.8 * slip_level
            for j, line in enumerate(skid_lines):
                offset = (j - 2) * 0.08
                start = contact_world - (0.15 + 0.36 * j) * tangent + offset * normal
                end = start - np.sign(trace.slip_speed_mps[idx] if trace.slip_speed_mps[idx] != 0.0 else 1.0) * mark_len * tangent
                line.set_data([start[0], end[0]], [start[1], end[1]])
                line.set_alpha(0.18 + 0.80 * slip_level)
                line.set_linewidth(1.5 + 3.0 * slip_level)
            for j, puff in enumerate(smoke_puffs):
                phase_j = (j + 0.2 * idx) % len(smoke_puffs)
                center = contact_world - (0.5 + 0.25 * phase_j) * tangent + (0.45 + 0.10 * np.sin(idx * 0.2 + j)) * normal
                puff.center = tuple(center)
                puff.radius = 0.10 + 0.16 * slip_level + 0.025 * j
                puff.set_alpha((0.05 + 0.20 * slip_level) * (1.0 - 0.10 * j))
        else:
            for line in skid_lines:
                line.set_data([], [])
            for puff in smoke_puffs:
                puff.set_alpha(0.0)

        scene_info.set_text(
            f"t = {trace.time_s[idx]:6.2f} s\n"
            f"distance = {trace.vehicle_position_m[idx]:7.2f} m\n"
            f"grade = {trace.grade_deg[idx]:7.2f} deg\n"
            f"terrain μ = {trace.terrain_mu[idx]:6.2f}\n"
            f"segment = {trace.terrain_segment[idx]}\n"
            f"slip speed = {trace.slip_speed_mps[idx]:+7.3f} m/s\n"
            f"slip ratio = {trace.slip_ratio[idx]:+7.3f}\n"
            f"tire util = {trace.tire_utilization[idx]:7.3f}\n"
            f"tire force = {trace.tire_force_n[idx]:8.1f} N\n"
            f"primary / secondary = {trace.primary_rpm[idx]:6.0f} / {trace.secondary_rpm[idx]:6.0f} rpm\n"
            f"shift = {trace.shift_mm[idx]:7.2f} mm\n"
            f"rate = {state.playback_speed:4.2f}×"
        )

        # Plot cursors and current markers.
        speed_cursor.set_xdata([trace.time_s[idx], trace.time_s[idx]])
        speed_vehicle_marker.set_data([trace.time_s[idx]], [trace.vehicle_speed_mps[idx] * 3.6])
        speed_patch_marker.set_data([trace.time_s[idx]], [trace.wheel_patch_speed_mps[idx] * 3.6])
        slip_ratio_cursor.set_xdata([trace.time_s[idx], trace.time_s[idx]])
        slip_ratio_marker.set_data([trace.time_s[idx]], [trace.slip_ratio[idx]])
        rpm_cursor.set_xdata([trace.time_s[idx], trace.time_s[idx]])
        primary_marker.set_data([trace.time_s[idx]], [trace.primary_rpm[idx]])
        secondary_marker.set_data([trace.time_s[idx]], [trace.secondary_rpm[idx]])
        shift_current.set_data([trace.secondary_rpm[idx]], [trace.primary_rpm[idx]])
        shift_vline.set_xdata([trace.secondary_rpm[idx], trace.secondary_rpm[idx]])
        shift_hline.set_ydata([trace.primary_rpm[idx], trace.primary_rpm[idx]])
        nonlocal _slider_update_active
        _slider_update_active = True
        try:
            time_slider.set_val(float(trace.time_s[idx]))
        finally:
            _slider_update_active = False
        return []

    def _time_to_index(sim_time_s: float) -> int:
        idx = int(np.searchsorted(trace.time_s, float(sim_time_s), side="left"))
        return max(0, min(frame_count - 1, idx))

    def _seek_to_index(new_index: int, *, pause: bool = True) -> None:
        state.current_index = max(0, min(frame_count - 1, int(new_index)))
        state.sim_time_s = float(trace.time_s[state.current_index])
        state.last_wall_time_s = time.monotonic()
        if pause:
            state.paused = True
        state.manual_step = state.current_index

    def _seek_to_time(new_time_s: float, *, pause: bool = True) -> None:
        _seek_to_index(_time_to_index(float(new_time_s)), pause=pause)

    def on_slider_change(value):
        if _slider_update_active:
            return
        _seek_to_time(float(value), pause=True)
        update_artists(state.current_index)
        fig.canvas.draw_idle()

    def on_rate_slider_change(value):
        if _rate_slider_update_active:
            return
        state.playback_speed = max(0.05, min(4.0, float(value)))
        state.last_wall_time_s = time.monotonic()
        update_artists(state.current_index)
        fig.canvas.draw_idle()

    def _set_rate(value: float) -> None:
        nonlocal _rate_slider_update_active
        state.playback_speed = max(0.05, min(4.0, float(value)))
        state.last_wall_time_s = time.monotonic()
        _rate_slider_update_active = True
        try:
            rate_slider.set_val(state.playback_speed)
        finally:
            _rate_slider_update_active = False

    def on_key(event):
        key = event.key
        if key == " ":
            state.paused = not state.paused
            state.last_wall_time_s = time.monotonic()
        elif key == "right":
            _seek_to_index(state.current_index + 1, pause=True)
        elif key == "left":
            _seek_to_index(state.current_index - 1, pause=True)
        elif key in {"shift+right", "alt+right"}:
            _seek_to_time(state.sim_time_s + 1.0, pause=True)
        elif key in {"shift+left", "alt+left"}:
            _seek_to_time(state.sim_time_s - 1.0, pause=True)
        elif key == "pageup":
            _seek_to_time(state.sim_time_s + 5.0, pause=True)
        elif key == "pagedown":
            _seek_to_time(state.sim_time_s - 5.0, pause=True)
        elif key == "home":
            _seek_to_index(0, pause=True)
        elif key == "end":
            _seek_to_index(frame_count - 1, pause=True)
        elif key == "up":
            _set_rate(state.playback_speed * 1.25)
        elif key == "down":
            _set_rate(state.playback_speed / 1.25)
        elif key in {"1", "r"}:
            _set_rate(1.0)
        elif key == "escape":
            plt.close(fig)

    def on_click(event):
        if event.inaxes in {ax_speed, ax_slip_ratio, ax_rpm} and event.xdata is not None:
            _seek_to_time(float(event.xdata), pause=True)
            update_artists(state.current_index)
            fig.canvas.draw_idle()
        elif event.inaxes is ax_shift_curve and event.xdata is not None:
            idx = int(np.argmin((trace.secondary_rpm - float(event.xdata)) ** 2))
            _seek_to_index(idx, pause=True)
            update_artists(state.current_index)
            fig.canvas.draw_idle()

    def next_frame_index(_frame_number: int) -> int:
        now = time.monotonic()
        wall_dt = max(0.0, now - state.last_wall_time_s)
        state.last_wall_time_s = now

        if state.manual_step is not None:
            idx = max(0, min(frame_count - 1, int(state.manual_step)))
            state.current_index = idx
            state.sim_time_s = float(trace.time_s[idx])
            state.manual_step = None
            return idx

        if not state.paused:
            state.sim_time_s = min(float(trace.time_s[-1]), state.sim_time_s + wall_dt * state.playback_speed)
            idx = _time_to_index(state.sim_time_s)
            state.current_index = idx
            if idx >= frame_count - 1:
                state.paused = True
            return idx

        return state.current_index

    time_slider.on_changed(on_slider_change)
    rate_slider.on_changed(on_rate_slider_change)
    fig.canvas.mpl_connect("key_press_event", on_key)
    fig.canvas.mpl_connect("button_press_event", on_click)
    update_artists(0)
    anim = animation.FuncAnimation(
        fig,
        lambda frame_number: update_artists(next_frame_index(frame_number)),
        interval=interval_ms,
        blit=False,
        repeat=False,
        cache_frame_data=False,
    )
    return fig, anim


def launch_playback_from_trace(trace_path: Path, *, playback_speed: float = 1.0, title: str | None = None, block: bool = True):
    trace = load_trace_csv(trace_path)
    playback_title = title or f"Tire-slip playback: {trace_path.stem}"
    fig, anim = build_playback_figure(trace, title=playback_title, playback_speed=playback_speed)
    # Keep a reference on the figure so the animation is not garbage-collected.
    setattr(fig, "_tire_slip_animation", anim)
    plt.show(block=block)
    return fig, anim


def parse_args(argv: Sequence[str] | None = None):
    parser = argparse.ArgumentParser(description="Play back a tire-slip terrain trace as a toy-car animation.")
    parser.add_argument("--trace", type=Path, default=None, help="Direct path to a *_trace.csv file.")
    parser.add_argument("--run-dir", type=Path, default=Path("outputs/tire_slip_terrain"), help="Root output directory created by run_tire_slip_terrain_response.py")
    parser.add_argument("--case", type=str, default=None, help="Case name or slug; used to resolve a trace under --run-dir.")
    parser.add_argument("--playback-speed", type=float, default=1.0, help="Real-time multiplier for playback.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    trace_path = resolve_trace_path(trace=args.trace, run_dir=args.run_dir, case=args.case)
    launch_playback_from_trace(trace_path, playback_speed=args.playback_speed)


if __name__ == "__main__":
    main()
