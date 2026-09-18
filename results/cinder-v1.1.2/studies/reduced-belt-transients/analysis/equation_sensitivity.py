"""Direct sensitivity analysis of the surviving reduced-belt equations.

This module does not integrate a trajectory.  It evaluates the coefficients in
CINDER's final tension-loop equation as functions of shift geometry and contact
traction utilization, then turns them into driver thresholds such as the shift
acceleration required for a 10% contribution relative to the contact-force
scale.  The purpose is to make the transient terms interpretable outside any
single Baja trajectory.
"""
from __future__ import annotations

# --- results study-local import bootstrap ---
from pathlib import Path as _ResultsPath
import sys as _results_sys

_results_file = _ResultsPath(__file__).resolve()
_results_study_root = next(
    (parent for parent in _results_file.parents if (parent / "study.json").is_file()),
    None,
)
if _results_study_root is None:
    raise RuntimeError(f"Could not locate study root for {_results_file}")
_results_release_root = _results_study_root.parents[1]
for _results_path in (str(_results_study_root), str(_results_release_root)):
    while _results_path in _results_sys.path:
        _results_sys.path.remove(_results_path)
_results_sys.path.insert(0, str(_results_release_root))
_results_sys.path.insert(0, str(_results_study_root))
# --- end results study-local import bootstrap ---


from math import exp, expm1, isfinite, sin
from pathlib import Path
from typing import Any

import numpy as np

from infrastructure.belt_terms import contact_coefficients
from infrastructure.study_support import write_json, write_rows

_SMALL = 1.0e-4
_EPS = 1.0e-15


def _phi_minus(z: float) -> float:
    if abs(z) < _SMALL:
        return 1.0 - z / 2.0 + z**2 / 6.0 - z**3 / 24.0 + z**4 / 120.0
    return -expm1(-z) / z


def _psi_minus(z: float) -> float:
    if abs(z) < _SMALL:
        return 0.5 - z / 6.0 + z**2 / 24.0 - z**3 / 120.0 + z**4 / 720.0
    return (z + expm1(-z)) / z**2


def contact_coefficients_from_lambda(*, traction_lambda: float, wrap_angle: float, sin_beta: float) -> tuple[float, float]:
    """Evaluate the exact regular H and G coefficients from signed lambda."""
    z = float(traction_lambda) * float(wrap_angle) / float(sin_beta)
    return contact_coefficients(
        wrap_angle=float(wrap_angle),
        sin_beta=float(sin_beta),
        phi_minus=_phi_minus(z),
        psi_minus=_psi_minus(z),
        exp_neg=exp(-z),
    )


def transient_coefficients(
    *,
    linear_density: float,
    primary_radius_cm: float,
    secondary_radius_cm: float,
    primary_d_radius_ds: float,
    secondary_d_radius_ds: float,
    primary_d2_radius_ds2: float,
    secondary_d2_radius_ds2: float,
    primary_H: float,
    secondary_H: float,
) -> dict[str, float]:
    q = float(linear_density)
    rp = float(primary_radius_cm)
    rs = float(secondary_radius_cm)
    rpp = float(primary_d_radius_ds)
    rsp = float(secondary_d_radius_ds)
    rpp2 = float(primary_d2_radius_ds2)
    rsp2 = float(secondary_d2_radius_ds2)
    return {
        "shift_acceleration_N_per_mps2": -2.0 * q * (rp * rpp - rs * rsp),
        "path_curvature_N_per_m2ps2": -2.0 * q * (rp * rpp2 - rs * rsp2),
        "belt_acceleration_N_per_mps2": q * (primary_H * rp - secondary_H * rs),
        "moving_radius_N_per_m2ps2": q * (primary_H * rpp - secondary_H * rsp),
    }


def driver_thresholds(
    *, coefficients: dict[str, float], contact_scale_N: float, fraction: float
) -> dict[str, float]:
    """Return kinematic drivers required for ``fraction * contact_scale_N``."""
    target = float(fraction) * float(contact_scale_N)
    if target < 0.0:
        raise ValueError("contact_scale_N and fraction must be non-negative.")
    ka = abs(float(coefficients["shift_acceleration_N_per_mps2"]))
    kc = abs(float(coefficients["path_curvature_N_per_m2ps2"]))
    kb = abs(float(coefficients["belt_acceleration_N_per_mps2"]))
    km = abs(float(coefficients["moving_radius_N_per_m2ps2"]))
    return {
        "shift_acceleration_m_per_s2": target / ka if ka > _EPS else float("inf"),
        "shift_speed_curvature_m_per_s": (target / kc) ** 0.5 if kc > _EPS else float("inf"),
        "belt_acceleration_m_per_s2": target / kb if kb > _EPS else float("inf"),
        "shift_speed_times_belt_speed_m2_per_s2": target / km if km > _EPS else float("inf"),
    }


def _belt_linear_density(document: dict[str, Any]) -> float:
    belt = document["assembly"]["geometry"]["belt"]
    rho = float(document["assembly"]["inertias"]["belt_density_kg_per_m3"])
    area = float(belt["height_m"]) * (
        float(belt["outer_width_m"]) + float(belt["inner_width_m"])
    ) / 2.0
    return rho * area


def _geometry_record(*, geometry: Any, shift_fraction: float, shift_m: float, q: float) -> dict[str, float]:
    coeff = transient_coefficients(
        linear_density=q,
        primary_radius_cm=geometry.primary.center_of_mass,
        secondary_radius_cm=geometry.secondary.center_of_mass,
        primary_d_radius_ds=geometry.primary.d_center_of_mass_ds,
        secondary_d_radius_ds=geometry.secondary.d_center_of_mass_ds,
        primary_d2_radius_ds2=geometry.primary.d2_center_of_mass_ds2,
        secondary_d2_radius_ds2=geometry.secondary.d2_center_of_mass_ds2,
        primary_H=0.0,
        secondary_H=0.0,
    )
    return {
        "active_shift_fraction": float(shift_fraction),
        "shift_position_m": float(shift_m),
        "primary_radius_cm_m": float(geometry.primary.center_of_mass),
        "secondary_radius_cm_m": float(geometry.secondary.center_of_mass),
        "primary_d_radius_ds": float(geometry.primary.d_center_of_mass_ds),
        "secondary_d_radius_ds": float(geometry.secondary.d_center_of_mass_ds),
        "primary_d2_radius_ds2_per_m": float(geometry.primary.d2_center_of_mass_ds2),
        "secondary_d2_radius_ds2_per_m": float(geometry.secondary.d2_center_of_mass_ds2),
        "primary_wrap_angle_rad": float(geometry.primary_wrap_angle),
        "secondary_wrap_angle_rad": float(geometry.secondary_wrap_angle),
        "K_shift_acceleration_N_per_mps2": coeff["shift_acceleration_N_per_mps2"],
        "K_path_curvature_N_per_m2ps2": coeff["path_curvature_N_per_m2ps2"],
    }


def build_equation_sensitivity(
    *,
    system: Any,
    document: dict[str, Any],
    output_dir: Path,
    shift_points: int = 41,
    utilization_points: int = 31,
) -> dict[str, Any]:
    """Generate geometry/contact sensitivity maps without integrating a trajectory."""
    if shift_points < 3 or utilization_points < 3:
        raise ValueError("Sensitivity grids require at least three points per axis.")
    model = system.cvt.model if hasattr(system, "cvt") else system.model
    spec = model.geometry.spec
    deadzone = float(spec.deadzone_shift)
    maximum = float(spec.max_shift)
    q = _belt_linear_density(document)
    beta = float(document["assembly"]["geometry"]["sheave_half_angle_rad"])
    sin_beta = sin(beta)
    mu_s = float(document["assembly"]["contact"]["static_friction_coefficient"])

    output_dir.mkdir(parents=True, exist_ok=True)
    geometry_rows: list[dict[str, float]] = []
    geometry_cache: dict[float, Any] = {}
    for xi in np.linspace(0.0, 1.0, shift_points):
        shift = deadzone + float(xi) * (maximum - deadzone)
        geometry = model.geometry.evaluate_engaged(shift)
        geometry_cache[float(xi)] = geometry
        geometry_rows.append(_geometry_record(geometry=geometry, shift_fraction=float(xi), shift_m=shift, q=q))
    write_rows(output_dir / "geometry_sensitivity.csv", geometry_rows)

    # Common-utilization paths expose the dependence on contact demand cleanly.
    # Drive uses the sign pattern observed in ordinary powered operation:
    # primary positive, secondary negative.  Overrun reverses both signs.
    contact_rows: list[dict[str, float | str]] = []
    representative_shifts = (0.10, 0.50, 0.90)
    for xi in representative_shifts:
        shift = deadzone + xi * (maximum - deadzone)
        geometry = model.geometry.evaluate_engaged(shift)
        for utilization in np.linspace(0.0, 0.95, utilization_points):
            magnitude = float(utilization) * mu_s
            for direction, sign in (("drive", 1.0), ("overrun", -1.0)):
                lp = sign * magnitude
                ls = -sign * magnitude
                Hp, Gp = contact_coefficients_from_lambda(
                    traction_lambda=lp,
                    wrap_angle=geometry.primary_wrap_angle,
                    sin_beta=sin_beta,
                )
                Hs, Gs = contact_coefficients_from_lambda(
                    traction_lambda=ls,
                    wrap_angle=geometry.secondary_wrap_angle,
                    sin_beta=sin_beta,
                )
                coeff = transient_coefficients(
                    linear_density=q,
                    primary_radius_cm=geometry.primary.center_of_mass,
                    secondary_radius_cm=geometry.secondary.center_of_mass,
                    primary_d_radius_ds=geometry.primary.d_center_of_mass_ds,
                    secondary_d_radius_ds=geometry.secondary.d_center_of_mass_ds,
                    primary_d2_radius_ds2=geometry.primary.d2_center_of_mass_ds2,
                    secondary_d2_radius_ds2=geometry.secondary.d2_center_of_mass_ds2,
                    primary_H=Hp,
                    secondary_H=Hs,
                )
                contact_rows.append({
                    "active_shift_fraction": xi,
                    "direction": direction,
                    "static_utilization_fraction": float(utilization),
                    "primary_lambda": lp,
                    "secondary_lambda": ls,
                    "primary_H": Hp,
                    "secondary_H": Hs,
                    "primary_G": Gp,
                    "secondary_G": Gs,
                    "K_belt_acceleration_N_per_mps2": coeff["belt_acceleration_N_per_mps2"],
                    "K_moving_radius_N_per_m2ps2": coeff["moving_radius_N_per_m2ps2"],
                })
    write_rows(output_dir / "contact_sensitivity.csv", contact_rows)

    # Independent primary/secondary traction magnitudes at three ratios.  This
    # prevents the common-utilization path from hiding asymmetric contact demand.
    pair_rows: list[dict[str, float]] = []
    pair_axis = np.linspace(0.0, 0.95, 11)
    for xi in representative_shifts:
        shift = deadzone + xi * (maximum - deadzone)
        geometry = model.geometry.evaluate_engaged(shift)
        for up in pair_axis:
            for us in pair_axis:
                lp = float(up) * mu_s
                ls = -float(us) * mu_s
                Hp, Gp = contact_coefficients_from_lambda(
                    traction_lambda=lp,
                    wrap_angle=geometry.primary_wrap_angle,
                    sin_beta=sin_beta,
                )
                Hs, Gs = contact_coefficients_from_lambda(
                    traction_lambda=ls,
                    wrap_angle=geometry.secondary_wrap_angle,
                    sin_beta=sin_beta,
                )
                coeff = transient_coefficients(
                    linear_density=q,
                    primary_radius_cm=geometry.primary.center_of_mass,
                    secondary_radius_cm=geometry.secondary.center_of_mass,
                    primary_d_radius_ds=geometry.primary.d_center_of_mass_ds,
                    secondary_d_radius_ds=geometry.secondary.d_center_of_mass_ds,
                    primary_d2_radius_ds2=geometry.primary.d2_center_of_mass_ds2,
                    secondary_d2_radius_ds2=geometry.secondary.d2_center_of_mass_ds2,
                    primary_H=Hp,
                    secondary_H=Hs,
                )
                pair_rows.append({
                    "active_shift_fraction": xi,
                    "primary_static_utilization_fraction": float(up),
                    "secondary_static_utilization_fraction": float(us),
                    "K_belt_acceleration_N_per_mps2": coeff["belt_acceleration_N_per_mps2"],
                    "K_moving_radius_N_per_m2ps2": coeff["moving_radius_N_per_m2ps2"],
                    "primary_G": Gp,
                    "secondary_G": Gs,
                })
    write_rows(output_dir / "contact_pair_sensitivity.csv", pair_rows)

    symmetry_error_H = 0.0
    symmetry_error_G = 0.0
    for xi in representative_shifts:
        shift = deadzone + xi * (maximum - deadzone)
        geometry = model.geometry.evaluate_engaged(shift)
        for u in np.linspace(0.0, 0.95, 20):
            lam = float(u) * mu_s
            for wrap in (geometry.primary_wrap_angle, geometry.secondary_wrap_angle):
                hp, gp = contact_coefficients_from_lambda(traction_lambda=lam, wrap_angle=wrap, sin_beta=sin_beta)
                hm, gm = contact_coefficients_from_lambda(traction_lambda=-lam, wrap_angle=wrap, sin_beta=sin_beta)
                symmetry_error_H = max(symmetry_error_H, abs(hp + hm))
                symmetry_error_G = max(symmetry_error_G, abs(gp - gm))

    summary = {
        "linear_density_kg_per_m": q,
        "sheave_half_angle_rad": beta,
        "static_friction_coefficient": mu_s,
        "engaged_shift_domain_m": [deadzone, maximum],
        "growth_laws": {
            "shift_acceleration": "F = K(s) * s_ddot",
            "path_curvature": "F = K(s) * s_dot^2",
            "belt_acceleration": "F = K(s, lambda_p, lambda_s) * v_b_dot",
            "moving_radius": "F = K(s, lambda_p, lambda_s) * s_dot * v_b",
            "whole_belt_inertia": "F = m_b * v_b_dot",
        },
        "contact_symmetry": {
            "H_is_odd_max_abs_error": symmetry_error_H,
            "G_is_even_max_abs_error": symmetry_error_G,
            "implication": "simultaneous traction reversal flips tangential transient coefficients but preserves G contact coefficients at fixed utilization magnitudes",
        },
    }
    write_json(output_dir / "summary.json", summary)
    _plot_equation_sensitivity(
        output_dir=output_dir,
        geometry_rows=geometry_rows,
        contact_rows=contact_rows,
    )
    return summary


def _plot_equation_sensitivity(*, output_dir: Path, geometry_rows: list[dict[str, Any]], contact_rows: list[dict[str, Any]]) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return

    x = np.asarray([float(row["active_shift_fraction"]) for row in geometry_rows])
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    ax.plot(x, [abs(float(row["K_shift_acceleration_N_per_mps2"])) for row in geometry_rows], label=r"$|K_{\ddot{s}}|$")
    ax.plot(x, [abs(float(row["K_path_curvature_N_per_m2ps2"])) for row in geometry_rows], label=r"$|K_{\dot{s}^2}|$")
    ax.set_xlabel("Active shift fraction [-]")
    ax.set_ylabel("Geometry response coefficient [channel-specific units]")
    ax.set_title("Equation sensitivity: radial coefficients across ratio")
    ax.legend()
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "radial_coefficients_vs_shift.png", dpi=180)
    plt.close(fig)

    drive = [row for row in contact_rows if row["direction"] == "drive"]
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    for xi in (0.10, 0.50, 0.90):
        subset = [row for row in drive if abs(float(row["active_shift_fraction"]) - xi) < 1.0e-12]
        ax.plot(
            [float(row["static_utilization_fraction"]) for row in subset],
            [abs(float(row["K_belt_acceleration_N_per_mps2"])) for row in subset],
            label=f"shift={xi:.1f}",
        )
    ax.set_xlabel(r"Common contact demand $|\lambda|/\mu_s$ [-]")
    ax.set_ylabel(r"$|K_{\dot{v}_b}|$ [N/(m/s²)]")
    ax.set_title("Equation sensitivity: belt-acceleration coupling grows with contact demand")
    ax.legend()
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "belt_acceleration_coefficient_vs_contact_demand.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    for xi in (0.10, 0.50, 0.90):
        subset = [row for row in drive if abs(float(row["active_shift_fraction"]) - xi) < 1.0e-12]
        ax.plot(
            [float(row["static_utilization_fraction"]) for row in subset],
            [abs(float(row["K_moving_radius_N_per_m2ps2"])) for row in subset],
            label=f"shift={xi:.1f}",
        )
    ax.set_xlabel(r"Common contact demand $|\lambda|/\mu_s$ [-]")
    ax.set_ylabel(r"$|K_{\dot{s}v_b}|$ [N/(m²/s²)]")
    ax.set_title("Equation sensitivity: moving-radius coupling across contact demand")
    ax.legend()
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "moving_radius_coefficient_vs_contact_demand.png", dpi=180)
    plt.close(fig)
