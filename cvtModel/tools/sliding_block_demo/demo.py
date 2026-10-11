"""Generate a physics-grounded CVTech-style sliding-weight demo.

From cvtModel: python -m tools.sliding_block_demo.demo --output /tmp/slide-demo
Optional:       python -m tools.sliding_block_demo.demo --output /tmp/slide-demo --html
The HTML is self-contained (requires `pip install plotly` when generating it).
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from math import pi
from pathlib import Path

import numpy as np

from .scenarios import EXAMPLES, make
from .sliding_block import Mechanism, Point, Profile, sweep, from_mapping


SCENE_LABELS = {
    "straight": "Straight ramps · Messick limit",
    "curved-cup": "Circular cup · straight opposing track",
    "both-curved": "Curved faces and curved tracks",
    "short-track": "Contact runs off finite track",
    "parallel": "Parallel constraints · singular",
}


# ----- Cross-section helpers -------------------------------------------------

def _mm(v: float | np.ndarray) -> float | np.ndarray:
    return 1000.0 * v


def _belt_radius(m: Mechanism, p: Point) -> float:
    """Stylized belt reference radius [m], tied to the solved block motion.

    This is only a visual cue so the patent-like cross-section has a belt that
    shifts outward as the movable sheave closes. It is deliberately not a belt
    mechanics solve.
    """
    if np.isfinite(p.radial):
        return float(np.clip(p.radial + 0.012, 0.056, 0.081))
    return float(np.clip(m.radius_ref + 0.012 + 0.010 * (p.x / max(m.x_max, 1e-9)), 0.056, 0.081))



def _spring_curve(x_center_mm: float, z0_mm: float, z1_mm: float, radius_mm: float = 3.6, turns: int = 6) -> tuple[np.ndarray, np.ndarray]:
    t = np.linspace(0.0, 2.0 * np.pi * turns, 260)
    z = z0_mm + (z1_mm - z0_mm) * t / t[-1]
    x = x_center_mm + radius_mm * np.sin(t)
    return x, z



def _sheave_faces(x_mm: np.ndarray, x_shift_mm: float) -> tuple[np.ndarray, np.ndarray]:
    """Return stylized lower and upper belt-contact face positions [mm]."""
    # Lower face is fixed. Upper face translates upward by approximately the
    # same closure shown by the solver so the viewer tells the right kinematic
    # story even though the belt itself is only a reference wedge.
    z_lower = np.interp(x_mm, [18.0, 84.0], [1.0, 14.0])
    z_upper = np.interp(x_mm, [18.0, 84.0], [17.0 + x_shift_mm, 6.0 + x_shift_mm])
    return z_lower, z_upper



def _belt_polygon(belt_r_mm: float, z_lower: float, z_upper: float) -> np.ndarray:
    # A simple trapezoid located between the sheave faces.
    inner = max(51.0, belt_r_mm - 6.0)
    outer = min(84.0, belt_r_mm + 4.0)
    low0 = np.interp(inner, [18.0, 84.0], [1.0, 14.0]) + 0.7
    low1 = np.interp(outer, [18.0, 84.0], [1.0, 14.0]) + 0.7
    up0 = np.interp(inner, [18.0, 84.0], [17.0, 6.0]) + (z_upper - np.interp(outer, [18.0, 84.0], [6.0, 6.0])) - 0.7
    # Use actual local upper point values to keep the wedge inside the faces.
    up0 = z_upper - 0.7 - 0.35 * (outer - inner)
    up1 = z_upper - 0.7
    return np.array([[inner, low0], [outer, low1], [outer, up1], [inner, up0]])



def _draw_cross_section_context(axis, m: Mechanism, p: Point) -> None:
    """Draw a patent-style cross-section around the exact solved contact geometry."""
    from matplotlib.patches import Polygon, Rectangle

    # Shaft / hub.
    shaft = Rectangle((0.0, -3.0), 15.0, 6.0, facecolor="#d7dde6", edgecolor="#808999", lw=1.4, zorder=0)
    axis.add_patch(shaft)
    hub = Rectangle((12.5, -5.0), 6.5, 10.0, facecolor="#c4ccd8", edgecolor="#7e8797", lw=1.3, zorder=0)
    axis.add_patch(hub)
    axis.axhline(0.0, color="#bfc7d3", lw=1.0, ls=(0, (3, 3)), zorder=0)

    # Stylized sheave bodies and simple belt reference.
    x_mm = np.linspace(18.0, 86.0, 300)
    x_shift_mm = float(_mm(p.x))
    lower_face, upper_face = _sheave_faces(x_mm, x_shift_mm)
    lower_poly = np.vstack([
        np.column_stack([x_mm, lower_face]),
        np.array([[86.0, 18.5], [25.0, 10.5], [18.0, 7.0], [18.0, 1.0]])
    ])
    upper_poly = np.vstack([
        np.array([[18.0, 17.0 + x_shift_mm], [25.0, 13.8 + x_shift_mm], [86.0, 18.0 + x_shift_mm], [86.0, 22.5 + x_shift_mm]]),
        np.column_stack([x_mm[::-1], upper_face[::-1]])
    ])
    axis.add_patch(Polygon(lower_poly, closed=True, facecolor="#edf1f6", edgecolor="#7f8794", lw=1.4, zorder=1))
    axis.add_patch(Polygon(upper_poly, closed=True, facecolor="#eef1f6", edgecolor="#7f8794", lw=1.4, zorder=1))

    if np.isfinite(p.radial):
        belt_r_mm = _mm(_belt_radius(m, p))
    else:
        belt_r_mm = _mm(_belt_radius(m, p))
    belt_outer = np.interp(belt_r_mm, x_mm, upper_face)
    belt_inner = np.interp(belt_r_mm, x_mm, lower_face)
    belt = _belt_polygon(belt_r_mm, belt_inner, belt_outer)
    axis.add_patch(Polygon(belt, closed=True, facecolor="#3f454f", edgecolor="#20252c", alpha=0.18, lw=1.0, zorder=2))

    # Reaction cup / housing around the block.
    cup = np.array([
        [11.0, -2.0], [14.0, -11.0], [18.0, -15.0], [30.0, -18.5], [47.0, -18.0],
        [64.0, -16.0], [74.0, -12.5], [79.0, -8.5], [82.0, -5.0], [84.0, -1.5],
        [84.0, 1.5], [80.0, 0.0], [77.0, -2.4], [70.0, -6.5], [56.0, -8.5],
        [44.0, -6.5], [34.0, -3.6], [25.0, -1.3], [18.0, 0.5], [14.0, 1.4], [11.0, 1.4],
    ])
    axis.add_patch(Polygon(cup, closed=True, facecolor="#f1f3f6", edgecolor="#8b919b", lw=1.4, zorder=0.8))

    # Spring around the shaft.
    sx, sz = _spring_curve(22.5, -10.0, 1.3 + 0.65 * x_shift_mm, radius_mm=3.2, turns=5)
    axis.plot([22.5, 22.5], [-11.5, 3.0 + 0.65 * x_shift_mm], color="#7c828e", lw=1.2, zorder=2)
    axis.plot(sx, sz, color="#586171", lw=1.5, zorder=2)

    # Simple connectors from the moving sheave body to the moving track region.
    axis.plot([31.0, 39.0], [10.0 + 0.55 * x_shift_mm, 7.0 + 0.30 * x_shift_mm], color="#8a8f99", lw=2.2, zorder=1.5)
    axis.plot([36.0, 43.5], [8.5 + 0.48 * x_shift_mm, 4.0 + 0.16 * x_shift_mm], color="#8a8f99", lw=2.2, zorder=1.5)
    axis.plot([18.0, 84.0], [lower_face[0], lower_face[-1]], alpha=0)  # keep autoscale stable if reused



def _render_geometry(axis, m: Mechanism, p: Point) -> None:
    """Patent-like section view plus exact solved tracks, contacts and block."""
    from matplotlib.patches import Polygon

    _draw_cross_section_context(axis, m, p)

    lower = m.lower_track
    upper = m.upper_track
    rlo = max(lower.left, upper.left)
    rhi = min(lower.right, upper.right)
    rgrid = np.linspace(rlo, rhi, 400)
    low_y = np.array([lower.value(float(r)) for r in rgrid])
    up_y = np.array([upper.value(float(r)) + p.x for r in rgrid])

    axis.plot(_mm(rgrid), _mm(low_y), color="#187b8b", lw=3.0, label="fixed reaction surface", zorder=4)
    axis.plot(_mm(rgrid), _mm(up_y), color="#b27035", lw=3.0, label="moving sheave ramp (+x)", zorder=4)
    axis.fill_between(_mm(rgrid), _mm(low_y) - 1.8, _mm(low_y), color="#187b8b", alpha=.10, zorder=3.5)
    axis.fill_between(_mm(rgrid), _mm(up_y), _mm(up_y) + 1.8, color="#b27035", alpha=.10, zorder=3.5)

    if np.isfinite(p.radial):
        u = np.linspace(m.lower_face.left, m.lower_face.right, 140)
        lower_block = np.array([m.lower_face.value(float(t)) for t in u]) + p.axial
        upper_block = np.array([m.upper_face.value(float(t)) for t in u]) + p.axial
        poly = np.vstack((np.column_stack((p.radial + u, lower_block)),
                          np.column_stack((p.radial + u[::-1], upper_block[::-1]))))
        axis.add_patch(Polygon(_mm(poly), closed=True, fc="#8ea4c8", ec="#284978", lw=1.8,
                               alpha=.80, label="sliding weight", zorder=5))
        axis.scatter([_mm(p.radial)], [_mm(p.axial)], s=72, c="#1f2b3c", zorder=7)
        axis.annotate("COM", (_mm(p.radial), _mm(p.axial)), xytext=(5, 6),
                      textcoords="offset points", fontsize=9, weight="bold")

        # Faint COM path for geometric intuition.
        x_path = np.linspace(0.0, m.x_max, 55)
        path = sweep(m, n=len(x_path))
        valid = [(q.radial, q.axial) for q in path if np.isfinite(q.radial) and np.isfinite(q.axial)]
        if valid:
            axis.plot([_mm(r) for r, _ in valid], [_mm(z) for _, z in valid], color="#4a5d80", lw=1.0, ls=(0, (2, 2)), alpha=0.75, zorder=3)

        for c, N, color in ((p.lower, p.N_lower, "#007f85"), (p.upper, p.N_upper, "#bc4e46")):
            if c is None:
                continue
            axis.scatter([_mm(c.radial)], [_mm(c.axial)], s=50, c=color, edgecolors="white", zorder=7)
            if np.isfinite(N):
                vec = np.array(c.normal) * 5.0 * (1 if N >= 0 else -1)
                axis.annotate("", xy=(_mm(c.radial) + vec[0], _mm(c.axial) + vec[1]),
                              xytext=(_mm(c.radial), _mm(c.axial)),
                              arrowprops=dict(arrowstyle="-|>", lw=2.2, color=color,
                                              linestyle="solid" if N >= 0 else "dashed"), zorder=8)
        axis.annotate("centrifugal", xy=(_mm(p.radial) + 9.0, _mm(p.axial) - 2.2),
                      xytext=(_mm(p.radial) + 2.5, _mm(p.axial) - 2.2),
                      arrowprops=dict(arrowstyle="-|>", lw=2.0, color="#7858a6"),
                      fontsize=8.5, color="#6a469a", va="center", zorder=8)

    axis.set_xlabel("Radial distance from shaft [mm]")
    axis.set_ylabel("Axial coordinate [mm]")
    axis.set_title(f"Primary cross-section at closure x = {_mm(p.x):.1f} mm")
    axis.set_xlim(0.0, 90.0)
    axis.set_ylim(-22.0, 30.0)
    axis.grid(alpha=.12)
    axis.set_aspect("equal")
    axis.legend(fontsize=8, loc="upper right")


def static_report(output: Path, name: str, *, mechanism: Mechanism | None = None, rpm: float = 2600.0, shift_accel: float = 0.0) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    m = mechanism if mechanism is not None else make(name)
    omega = rpm * 2 * pi / 60
    pts = sweep(m, n=101, omega=omega, xddot=shift_accel)
    middle = pts[len(pts) // 2]
    xs = np.array([p.x for p in pts]) * 1000

    def arr(attr: str) -> np.ndarray:
        return np.array([getattr(p, attr) for p in pts])

    fig = plt.figure(figsize=(13.8, 9.4), constrained_layout=True)
    grid = fig.add_gridspec(2, 2)
    geom = fig.add_subplot(grid[0, 0])
    _render_geometry(geom, m, middle)

    inertia = fig.add_subplot(grid[0, 1])
    inertia2 = inertia.twinx()
    inertia.plot(xs, arr("M_f"), color="#2a6b8d", label=r"$M_f$ [kg]")
    inertia.plot(xs, arr("M_f_prime") / 100, color="#2a6b8d", ls="--", label=r"$M_f'/100$ [kg/m]")
    inertia2.plot(xs, 1000 * arr("J_f"), color="#b77032", label=r"$J_f$ [10$^{-3}$ kg m$^2$]")
    inertia2.plot(xs, 1000 * arr("J_f_prime"), color="#bd4380", ls=":", label=r"$J_f'$ [10$^{-3}$ kg m]")
    inertia.axvline(middle.x * 1000, alpha=.45, ls=":", color="black")
    inertia.set_xlabel("Sheave closure x [mm]")
    inertia.set_ylabel("Effective shift mass [kg]")
    inertia2.set_ylabel("Shaft inertia / slope (scaled)")
    inertia.set_title("The four v4 mechanism functions")
    inertia.grid(alpha=.18)
    lines = inertia.get_lines()[:2] + inertia2.get_lines()
    inertia.legend(lines, [p.get_label() for p in lines], fontsize=8, loc="upper left")

    loads = fig.add_subplot(grid[1, 0])
    loads.plot(xs, arr("N_lower"), color="#007f85", label="fixed-surface contact normal")
    loads.plot(xs, arr("N_upper"), color="#bc4e46", label="moving-ramp contact normal")
    loads.plot(xs, arr("F_interface"), color="#65429d", ls="--", label="v4 axial mechanism force")
    loads.axhline(0, color="#333", lw=1)
    loads.set_xlabel("Sheave closure x [mm]")
    loads.set_ylabel("TOTAL force [N]")
    loads.set_title(f"Contact feasibility · {rpm:.0f} RPM · x¨ = {shift_accel:.0f} m/s²")
    loads.grid(alpha=.18)
    loads.legend(fontsize=8, loc="upper left")

    map_ax = fig.add_subplot(grid[1, 1])
    omega_map = 80.0
    accelerations = np.linspace(-500, 700, 97)
    heat = np.zeros((len(accelerations), len(pts)))
    for j, acc in enumerate(accelerations):
        for i, p_i in enumerate(pts):
            if p_i.lower is None or p_i.upper is None:
                heat[j, i] = 2
                continue
            ar = p_i.r_prime * acc - p_i.radial * omega_map ** 2
            az = p_i.z_prime * acc
            A = np.column_stack((p_i.lower.normal, p_i.upper.normal))
            normals = np.linalg.solve(A, m.total_mass * np.array([ar, az]))
            heat[j, i] = 0 if all(normals >= -1e-7) else 1
    map_ax.pcolormesh(xs, accelerations, heat, cmap=ListedColormap(["#a1d5b5", "#e8a7a2", "#adacc0"]),
                      vmin=0, vmax=2, shading="nearest")
    map_ax.set_title("Operating-point admissibility at ω = 80 rad/s")
    map_ax.set_xlabel("Sheave closure x [mm]")
    map_ax.set_ylabel("Assumed sheave acceleration x¨ [m/s²]")
    map_ax.text(.02, .03, "green: 2 compressive contacts\nred: liftoff\ngrey: geometric invalidity",
                transform=map_ax.transAxes, fontsize=9, va="bottom",
                bbox=dict(facecolor="white", edgecolor="#ddd", alpha=.9))
    fig.suptitle(
        f"Sliding-block admissibility · {SCENE_LABELS.get(name, m.name)}\n"
        "Exact 2-D contact geometry inside a stylized primary cross-section · synthetic example, not measured CVTech CAD",
        weight="bold", fontsize=14
    )
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"{name}_mechanism.png"
    fig.savefig(target, dpi=145, bbox_inches="tight")
    plt.close(fig)
    return target


def _html_data(custom: Mechanism | None = None) -> dict:
    scenes = {}
    for name in ((*EXAMPLES, "custom") if custom else EXAMPLES):
        m = custom if name == "custom" else make(name)
        points = sweep(m, n=76, omega=280)

        def jsonify_contact(c):
            if c is None:
                return None
            return dict(u=c.u, R=c.radial, Z=c.axial, slope=c.slope, norm=c.normal, mode=c.mode)

        scenes[name] = {
            "title": SCENE_LABELS.get(name, m.name),
            "mass": m.total_mass,
            "count": m.display_count,
            "kg": m.gyration_radius,
            "xmax": m.x_max,
            "radius_ref": m.radius_ref,
            "lower_track": asdict(m.lower_track),
            "upper_track": asdict(m.upper_track),
            "lower_face": asdict(m.lower_face),
            "upper_face": asdict(m.upper_face),
            "points": [{
                "x": p.x,
                "r": p.radial if np.isfinite(p.radial) else None,
                "z": p.axial if np.isfinite(p.axial) else None,
                "rp": p.r_prime if np.isfinite(p.r_prime) else None,
                "zp": p.z_prime if np.isfinite(p.z_prime) else None,
                "rpp": p.r_second if np.isfinite(p.r_second) else None,
                "zpp": p.z_second if np.isfinite(p.z_second) else None,
                "Mf": p.M_f if np.isfinite(p.M_f) else None,
                "Mfp": p.M_f_prime if np.isfinite(p.M_f_prime) else None,
                "J": p.J_f if np.isfinite(p.J_f) else None,
                "Jp": p.J_f_prime if np.isfinite(p.J_f_prime) else None,
                "lower": jsonify_contact(p.lower),
                "upper": jsonify_contact(p.upper),
                "issues": list(p.issues),
            } for p in points],
        }
    return scenes


def interactive_html(output: Path, custom: Mechanism | None = None) -> Path:
    try:
        from plotly.offline import get_plotlyjs
    except ImportError as exc:
        raise RuntimeError("plotly is only needed for --html: pip install plotly") from exc
    template = Path(__file__).with_name("template.html").read_text(encoding="utf-8")
    html = template.replace("/*__SCENES__*/", "const SCENES = " + json.dumps(_html_data(custom), separators=(",", ":")) + ";")
    html = html.replace("/*__PLOTLY__*/", get_plotlyjs())
    output.mkdir(parents=True, exist_ok=True)
    dest = output / "sliding_block_explorer.html"
    dest.write_text(html, encoding="utf-8")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("sliding_block_outputs"))
    parser.add_argument("--html", action="store_true", help="also generate a standalone offline browser explorer (plotly)")
    parser.add_argument("--scenario", choices=(*EXAMPLES, "all"), default="all")
    parser.add_argument("--config", type=Path, help="custom measured/synthetic mechanism JSON (do not silently re-zero measured tracks)")
    parser.add_argument("--write-example-config", type=Path, help="write editable, complete example JSON and exit")
    args = parser.parse_args()
    if args.write_example_config:
        args.write_example_config.parent.mkdir(parents=True, exist_ok=True)
        args.write_example_config.write_text(json.dumps(asdict(make("both-curved")), indent=2) + "\n", encoding="utf-8")
        print("Wrote example configuration:", args.write_example_config)
        return
    custom = from_mapping(json.loads(args.config.read_text(encoding="utf-8"))) if args.config else None
    examples = ("custom",) if custom else (EXAMPLES if args.scenario == "all" else (args.scenario,))
    for name in examples:
        mechanism = custom if custom else make(name)
        file = static_report(args.output, name, mechanism=mechanism)
        points = sweep(mechanism, n=101)
        print(f"{name:13} {sum(p.admissible for p in points):3}/{len(points)} admissible at 350 rad/s, x¨=0; {file}")
    if args.html:
        print("Interactive offline HTML:", interactive_html(args.output, custom))


if __name__ == "__main__":
    main()
