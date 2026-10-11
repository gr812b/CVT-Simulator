"""Generate a physics-grounded CVTech-style sliding-weight demo.

From cvtModel: python -m tools.sliding_block_demo.demo --output /tmp/slide-demo
Optional:       python -m tools.sliding_block_demo.demo --output /tmp/slide-demo --html
The HTML is self-contained. Install requirements-demo.txt before generating it.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from math import pi
from pathlib import Path

import numpy as np

from .scenarios import EXAMPLES, make
from .sliding_block import Mechanism, sweep, from_mapping
from .section import build_section, section_frame, render_section


SCENE_LABELS = {
    "straight": "Straight ramps · Messick limit",
    "curved-cup": "Circular cup · straight opposing track",
    "both-curved": "Curved faces and curved tracks",
    "short-track": "Finite track-domain limit",
    "parallel": "Parallel constraints · singular",
}


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
    section = build_section(m, pts)
    render_section(geom, section, section_frame(section, m, middle), middle)

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
        "Finite reference solids with unchanged active contact profiles · synthetic geometry, not measured CVTech CAD",
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
        section = build_section(m, points)

        def jsonify_contact(c):
            if c is None:
                return None
            return dict(u=c.u, R=c.radial, Z=c.axial, slope=c.slope, norm=c.normal, mode=c.mode)

        scenes[name] = {
            "title": SCENE_LABELS.get(name, m.name),
            "section": asdict(section),
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
                "section": section_frame(section, m, p),
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
                "issues": [issue for issue in p.issues if "contact liftoff" not in issue],
            } for p in points],
        }
    return scenes


def interactive_html(output: Path, custom: Mechanism | None = None) -> Path:
    try:
        from plotly.offline import get_plotlyjs
    except ImportError as exc:
        raise RuntimeError("plotly is only needed for --html: pip install plotly") from exc
    template = Path(__file__).with_name("template.html").read_text(encoding="utf-8")
    html = template.replace("/*__SCENES__*/", "const SCENES = " + json.dumps(_html_data(custom), separators=(",", ":"), allow_nan=False).replace("</", "<\\/") + ";")
    html = html.replace("/*__PLOTLY__*/", get_plotlyjs())
    html = html.replace("/*__SECTION_VIEW__*/", Path(__file__).with_name("section_view.js").read_text(encoding="utf-8"))
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
