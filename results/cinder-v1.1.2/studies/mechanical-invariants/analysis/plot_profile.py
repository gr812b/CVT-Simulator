"""Plot the verified primary wrap profiles without running a simulation.

The retained fields and verification record are checked together before any
figure is written. Run `python plot_profile.py --help` for location overrides.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_verified_profiles(data: Path) -> tuple[dict, dict, dict]:
    """Check identity, geometry, full spatial fields and analytical integrals."""
    csv_path = data / "primary_wrap_profiles.csv"
    record = json.loads((data / "profile_verification.json").read_text())
    if digest(csv_path) != record["output_csv_sha256"]:
        raise ValueError("Spatial CSV does not match its reconstruction record.")
    if record["case_id"] != "both_slip_mm" or not record["state_continuous_exactly"]:
        raise ValueError("Expected the continuous-state first primary reversal.")
    with csv_path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 2002 or {r["side"] for r in rows} != {"before", "after"}:
        raise ValueError("Expected 1,001 wrap positions on each exact event side.")
    profiles, checks = {}, {}
    for side in ("before", "after"):
        selected = [r for r in rows if r["side"] == side]
        theta = np.array([float(r["theta_rad"]) for r in selected])
        normal = np.array([float(r["normal_N_per_rad"]) for r in selected])
        tension = np.array([float(r["tension_N"]) for r in selected])
        times = np.array([float(r["event_time_s"]) for r in selected])
        saved = record["sides"][side]
        phi = saved["primary_wrap_angle_rad"]
        if not all(np.all(np.isfinite(v)) for v in (theta, normal, tension, times)):
            raise ValueError("Nonfinite field data.")
        if len(theta) != 1001 or theta[0] != 0 or not np.all(np.diff(theta) > 0):
            raise ValueError("Invalid wrap-angle sampling.")
        if theta[-1] != phi or not np.all(times == record["event_time_s"]):
            raise ValueError("The retained fields must be at the exact same event.")
        if saved["audit_failures"] or np.min(normal) < 0 or np.min(tension) < 0:
            raise ValueError("The selected event must pass its local physical checks.")
        z = saved["exponential_parameter_z"]
        weight = theta / phi if abs(z) < 1e-10 else np.expm1(-z * theta / phi) / np.expm1(-z)
        expected_tension = saved["primary_tension_in_N"] + (
            saved["primary_tension_out_N"] - saved["primary_tension_in_N"]) * weight
        expected_normal = (expected_tension - saved["primary_radial_inertial_offset_N"]) / math.sin(saved["sheave_half_angle_rad"])
        if not np.allclose(tension, expected_tension, atol=1e-10, rtol=1e-12):
            raise ValueError("CSV tension differs from the analytical wrap field.")
        if not np.allclose(normal, expected_normal, atol=1e-10, rtol=1e-12):
            raise ValueError("CSV normal loading differs from the radial balance.")
        if not np.isclose(np.min(normal), saved["minimum_local_normal_N_per_rad"], atol=1e-10, rtol=1e-12):
            raise ValueError("The annotated minimum differs from the retained field.")
        # Independent closed-form integral of the exponential endpoint field.
        mean_weight = 0.5 if abs(z) < 1e-10 else -1.0 / np.expm1(-z) - 1.0 / z
        integral = phi * (normal[0] + (normal[-1] - normal[0]) * mean_weight)
        error = float(integral - saved["integrated_primary_normal_N"])
        if not math.isclose(integral, saved["integrated_primary_normal_N"], abs_tol=1e-7, rel_tol=1e-10):
            raise ValueError("Analytical profile integral differs from solved normal load.")
        profiles[side] = (theta, normal)
        checks[side] = {
            "spatial_rows": len(theta), "full_field_matches_analytical_solution": True,
            "minimum_normal_N_per_rad": float(normal.min()),
            "analytic_profile_integral_N": float(integral),
            "integral_minus_solved_normal_N": error,
        }
    if not np.array_equal(profiles["before"][0], profiles["after"][0]):
        raise ValueError("The comparison requires the same exact geometry.")
    if record["sides"]["before"]["cvt_state"] != record["sides"]["after"]["cvt_state"]:
        raise ValueError("State changed across the selected direction reversal.")
    return profiles, record, checks


def main(data: Path, output: Path) -> dict:
    profiles, record, checks = read_verified_profiles(data)
    output.mkdir(parents=True, exist_ok=True)
    style = {
        "font.family": "serif", "font.serif": ["cmr10"],
        "mathtext.fontset": "cm", "font.size": 10,
        "axes.labelsize": 10, "xtick.labelsize": 9, "ytick.labelsize": 9,
        "axes.formatter.use_mathtext": True, "axes.unicode_minus": False,
        "pdf.fonttype": 42, "ps.fonttype": 42,
        "axes.spines.top": False, "axes.spines.right": False,
    }
    colours = {"before": "#245A81", "after": "#B74724"}
    with plt.rc_context(style):
        fig, ax = plt.subplots(figsize=(6.2, 3.55))
        fig.subplots_adjust(left=.115, right=.975, bottom=.245, top=.965)
        for side, line_style in (("before", "--"), ("after", "-")):
            theta, normal = profiles[side]
            total = record["sides"][side]["integrated_primary_normal_N"]
            label = rf"{side.capitalize()} reversal: $N_p={total:.0f}$ N"
            ax.plot(theta, normal, color=colours[side], ls=line_style, lw=1.8, label=label)
            i = np.argmin(normal)
            ax.scatter(theta[i], normal[i], color=colours[side], s=17, zorder=4)
        phi = profiles["after"][0][-1]
        # Leader lines identify the exact endpoint values. The small positive
        # outgoing value lies visually at zero at this physically scaled axis.
        ax.annotate(rf"Minimum: ${profiles['after'][1].min():.3g}$ N/rad", xy=(0, profiles["after"][1][0]),
                    xytext=(.10, 60), color=colours["after"], fontsize=9,
                    arrowprops={"arrowstyle": "-", "color": colours["after"], "lw": .8})
        ax.annotate(rf"Minimum: ${profiles['before'][1].min():.3g}$ N/rad", xy=(phi, profiles["before"][1][-1]),
                    xytext=(phi-.025, 95), ha="right", color=colours["before"], fontsize=9,
                    arrowprops={"arrowstyle": "-", "color": colours["before"], "lw": .8})
        ax.axhline(0, color=".35", lw=.75, zorder=0)
        ax.set_xlim(-.025, phi + .025)
        ax.set_ylim(-35, 1230)
        ax.set_yticks([0, 200, 400, 600, 800, 1000, 1200])
        ax.set_xticks([0, 1, 2, phi], ["0\nEntrance", "1", "2", rf"$\phi_p={phi:.3f}$"+"\nExit"])
        ax.get_xticklabels()[-1].set_ha("right")
        ax.set_xlabel(r"Position around primary wrap, $\theta$ [rad]", labelpad=8)
        ax.set_ylabel(r"Local normal loading, $dN_p/d\theta$ [N/rad]")
        ax.grid(axis="y", color=".88", lw=.55)
        ax.set_axisbelow(True)
        legend = ax.legend(loc="upper center", bbox_to_anchor=(.46, 1.005),
                           frameon=False, fontsize=9.5, handlelength=2.4,
                           title=r"Area under each curve gives $N_p$", title_fontsize=9.5)
        legend._legend_box.align = "left"
        metadata = {"Creator": "CINDER Section 4.2.1 plot_profile.py",
                    "CreationDate": None, "ModDate": None}
        fig.savefig(output / "primary_wrap_profiles.pdf", metadata=metadata)
        fig.savefig(output / "primary_wrap_profiles.png", dpi=300)
        plt.close(fig)
    provenance = {
        "figure": "primary_wrap_profiles", "manuscript_label": "fig:verification_wrap_loading",
        "placement": "Appendix D.1 support; the main verification evidence is the case/result tables",
        "size_inches": [6.2, 3.55], "raster_dpi": 300,
        "case_id": record["case_id"], "event_time_s": record["event_time_s"],
        "mechanics_version": record["versions"]["cinder-cvt"],
        "mechanics_commit": record["frozen_source_commit"],
        "plotting_versions": {p: importlib.metadata.version(p) for p in ("numpy", "matplotlib")},
        "plot_script_sha256": digest(Path(__file__)),
        "data_sha256": digest(data / "primary_wrap_profiles.csv"),
        "reconstruction_record_sha256": digest(data / "profile_verification.json"),
        "transformations": {
            "field": "Analytical instantaneous primary wrap field on the exact two event sides; no interpolation through the event or fitting to extrema.",
            "coordinate": "theta=0 at entrance; theta=phi_p at exit, following the manuscript wrap-coordinate definition.",
            "axes": "Linear, physical radians and N/rad; zero baseline shown. Area is total N_p.",
            "annotations": "Totals rounded to nearest N; minima to three significant figures.",
        },
        "checks": checks,
        "outputs": {name: digest(output / name) for name in ("primary_wrap_profiles.pdf", "primary_wrap_profiles.png")},
    }
    (output / "primary_wrap_profiles_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    return provenance


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=HERE / "data")
    parser.add_argument("--output", type=Path, default=HERE.parent / "figures")
    arguments = parser.parse_args()
    result = main(arguments.data.resolve(), arguments.output.resolve())
    print(json.dumps(result["checks"], indent=2))
