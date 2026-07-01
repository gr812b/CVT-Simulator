"""Map stick residuals over positive trial friction utilizations.

This is a diagnostic only. It does *not* root-solve for lambdas or select a
contact branch. It freezes one snapshot and rows 2--5, then evaluates the
future stick residual map

    (lambda_p, lambda_s) -> (R_p, R_s)

across the positive utilization domain used by the current forward-drive
convention. Positive lambda_p represents primary-to-belt traction and
positive lambda_s represents belt-to-secondary traction; the pulley-specific
wrap equations already encode their opposite torque roles.

The plots deliberately use visual scales that make the zero contours readable:

* primary and secondary residual maps use a symmetric logarithmic colour scale
  centred at zero;
* the residual-norm panel uses a logarithmic colour scale;
* every zero contour is drawn with a black outline plus a high-contrast line.

Run from cvtModel/:

    python tools/preview_lambda_residual_map.py
    python tools/preview_lambda_residual_map.py --scenario active-shift
    python tools/preview_lambda_residual_map.py --resolution-scale 2 \
        --save artifacts/lambda_map.png --no-show

Use --resolution-scale to multiply the number of grid intervals in both lambda
directions. For the default 81-point grid, a scale of 2 gives 161×161 points,
and a scale of 4 gives 321×321 points.

The displayed zero contours are diagnostic contours only. Their intersection,
if one exists in the sampled domain, is what a later 2D stick-lambda root
solver will seek more accurately.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import sys

import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, SymLogNorm, TwoSlopeNorm
from matplotlib.lines import Line2D
import numpy as np

# Support both the normal src/cinder repository layout and direct overlays.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (_REPOSITORY_ROOT / "src", _REPOSITORY_ROOT):
    if (_candidate / "cinder").is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from baja_trial_baseline import BajaTrialBaseline, build_baja_trial_baseline
from cinder.dynamics import (
    CVTDynamicState,
    TrialEquationContext,
    TrialFrictionUtilization,
    build_state_fixed_equations,
    build_trial_six_by_six_system,
)

# Legacy test friction value. Replace with a model-owned contact property once
# friction is part of the production contact-law configuration.
DEFAULT_STATIC_UTILIZATION_LIMIT = 0.65
DEFAULT_MINIMUM_UTILIZATION = 0.01
DEFAULT_SAMPLES = 81
DEFAULT_RESIDUAL_LINTHRESH = 1.0
DEFAULT_RESIDUAL_CLIP_PERCENTILE = 99.0
DEFAULT_NORM_CLIP_PERCENTILE = 99.5

_PRIMARY_ZERO_CONTOUR_COLOR = "#00bcd4"
_SECONDARY_ZERO_CONTOUR_COLOR = "#ff4081"


@dataclass(frozen=True, slots=True)
class LambdaResidualMap:
    """All values sampled from one frozen snapshot and fixed row block."""

    primary_lambdas: np.ndarray
    secondary_lambdas: np.ndarray
    primary_residual: np.ndarray
    secondary_residual: np.ndarray
    residual_norm: np.ndarray
    condition_number: np.ndarray
    primary_torque: np.ndarray
    secondary_torque: np.ndarray
    determinant_jacobian: np.ndarray


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Map six-by-six stick residuals over positive lambda trials."
    )
    parser.add_argument(
        "--scenario",
        choices=("quasi-static", "active-shift"),
        default="quasi-static",
        help="Frozen engaged state to inspect.",
    )
    parser.add_argument(
        "--lambda-min",
        type=float,
        default=DEFAULT_MINIMUM_UTILIZATION,
        help="Smallest positive lambda sampled; exact zero is not yet supported.",
    )
    parser.add_argument(
        "--lambda-max",
        type=float,
        default=DEFAULT_STATIC_UTILIZATION_LIMIT,
        help="Largest positive lambda sampled.",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=DEFAULT_SAMPLES,
        help="Grid points per lambda direction.",
    )
    parser.add_argument(
        "--resolution-scale",
        type=float,
        default=1.0,
        help=(
            "Multiplier applied to the number of sampled lambda intervals in "
            "both directions. With the default 81-point grid, 2 gives 161×161 "
            "points and 4 gives 321×321 points."
        ),
    )
    parser.add_argument(
        "--residual-linthresh",
        type=float,
        default=DEFAULT_RESIDUAL_LINTHRESH,
        help=(
            "Half-width of the linear band around zero for the primary and "
            "secondary residual colour scales [m/s^2]."
        ),
    )
    parser.add_argument(
        "--residual-clip-percentile",
        type=float,
        default=DEFAULT_RESIDUAL_CLIP_PERCENTILE,
        help=(
            "Robust absolute-percentile limit for the signed residual colour "
            "scales. Larger outliers are saturated so zero contours stay visible."
        ),
    )
    parser.add_argument(
        "--norm-clip-percentile",
        type=float,
        default=DEFAULT_NORM_CLIP_PERCENTILE,
        help=(
            "Robust percentile limit for the log residual-norm colour scale. "
            "Larger values are saturated."
        ),
    )
    parser.add_argument(
        "--save",
        type=Path,
        help="Optional PNG/PDF/SVG output path.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Build and optionally save the figure without opening a window.",
    )
    args = parser.parse_args()

    if not isfinite(args.lambda_min) or args.lambda_min <= 0.0:
        parser.error("--lambda-min must be finite and strictly positive.")
    if not isfinite(args.lambda_max) or args.lambda_max <= args.lambda_min:
        parser.error("--lambda-max must be finite and greater than --lambda-min.")
    if args.samples < 5:
        parser.error("--samples must be at least 5.")
    if not isfinite(args.resolution_scale) or args.resolution_scale <= 0.0:
        parser.error("--resolution-scale must be finite and positive.")
    if not isfinite(args.residual_linthresh) or args.residual_linthresh <= 0.0:
        parser.error("--residual-linthresh must be finite and positive.")
    for option_name, value in (
        ("--residual-clip-percentile", args.residual_clip_percentile),
        ("--norm-clip-percentile", args.norm_clip_percentile),
    ):
        if not isfinite(value) or not 50.0 <= value <= 100.0:
            parser.error(f"{option_name} must lie between 50 and 100.")
    return args


def main() -> None:
    args = parse_arguments()
    effective_samples = _scaled_sample_count(
        base_samples=args.samples,
        resolution_scale=args.resolution_scale,
    )
    baseline = build_baja_trial_baseline()
    state = _select_state(baseline=baseline, scenario=args.scenario)
    snapshot = baseline.model.snapshot(state=state)
    fixed_equations = build_state_fixed_equations(snapshot=snapshot)

    residual_map = build_lambda_residual_map(
        snapshot=snapshot,
        fixed_equations=fixed_equations,
        lambda_min=args.lambda_min,
        lambda_max=args.lambda_max,
        samples=effective_samples,
    )
    _print_summary(
        scenario=args.scenario,
        state=state,
        snapshot=snapshot,
        residual_map=residual_map,
        base_samples=args.samples,
        resolution_scale=args.resolution_scale,
    )

    figure = plot_lambda_residual_map(
        scenario=args.scenario,
        residual_map=residual_map,
        residual_linthresh=args.residual_linthresh,
        residual_clip_percentile=args.residual_clip_percentile,
        norm_clip_percentile=args.norm_clip_percentile,
        effective_samples=effective_samples,
    )
    if args.save is not None:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(args.save, dpi=180)
        print(f"Saved {args.save}")
    if not args.no_show:
        plt.show()


def _scaled_sample_count(*, base_samples: int, resolution_scale: float) -> int:
    """Return an endpoint-preserving square-grid resolution.

    The user-facing scale multiplies intervals rather than points. This makes
    scale=2 turn 81 points into 161 points, preserving both lambda bounds.
    """

    base_intervals = max(base_samples - 1, 1)
    scaled_intervals = max(4, int(round(base_intervals * resolution_scale)))
    return scaled_intervals + 1


def _select_state(
    *,
    baseline: BajaTrialBaseline,
    scenario: str,
) -> CVTDynamicState:
    if scenario == "quasi-static":
        return baseline.quasi_static_state
    return baseline.active_shift_state


def build_lambda_residual_map(
    *,
    snapshot,
    fixed_equations,
    lambda_min: float,
    lambda_max: float,
    samples: int,
) -> LambdaResidualMap:
    """Sample residuals without invoking any lambda root-finding algorithm."""

    primary_lambdas = np.linspace(lambda_min, lambda_max, samples)
    secondary_lambdas = np.linspace(lambda_min, lambda_max, samples)
    shape = (secondary_lambdas.size, primary_lambdas.size)

    primary_residual = np.full(shape, np.nan)
    secondary_residual = np.full(shape, np.nan)
    condition_number = np.full(shape, np.nan)
    primary_torque = np.full(shape, np.nan)
    secondary_torque = np.full(shape, np.nan)

    for secondary_index, lambda_secondary in enumerate(secondary_lambdas):
        for primary_index, lambda_primary in enumerate(primary_lambdas):
            trial = TrialFrictionUtilization(
                primary_lambda=float(lambda_primary),
                secondary_lambda=float(lambda_secondary),
            )
            try:
                result = _solve_trial(
                    snapshot=snapshot,
                    fixed_equations=fixed_equations,
                    trial=trial,
                )
            except (ArithmeticError, ValueError, RuntimeError):
                # A later root solver will need a more explicit domain policy.
                # For the map, leave unsolved points blank rather than hiding
                # them behind arbitrary replacements.
                continue

            residual_primary, residual_secondary = _no_slip_acceleration_errors(
                snapshot=snapshot,
                unknowns=result.unknowns,
            )
            primary_residual[secondary_index, primary_index] = residual_primary
            secondary_residual[secondary_index, primary_index] = residual_secondary
            condition_number[secondary_index, primary_index] = result.condition_number
            primary_torque[secondary_index, primary_index] = result.unknowns.primary_torque
            secondary_torque[secondary_index, primary_index] = result.unknowns.secondary_torque

    residual_norm = np.hypot(primary_residual, secondary_residual)
    determinant_jacobian = _finite_difference_jacobian_determinant(
        primary_lambdas=primary_lambdas,
        secondary_lambdas=secondary_lambdas,
        primary_residual=primary_residual,
        secondary_residual=secondary_residual,
    )

    return LambdaResidualMap(
        primary_lambdas=primary_lambdas,
        secondary_lambdas=secondary_lambdas,
        primary_residual=primary_residual,
        secondary_residual=secondary_residual,
        residual_norm=residual_norm,
        condition_number=condition_number,
        primary_torque=primary_torque,
        secondary_torque=secondary_torque,
        determinant_jacobian=determinant_jacobian,
    )


def _solve_trial(*, snapshot, fixed_equations, trial: TrialFrictionUtilization):
    context = TrialEquationContext(
        snapshot=snapshot,
        friction_utilization=trial,
    )
    system = build_trial_six_by_six_system(
        fixed_equations=fixed_equations,
        trial_context=context,
    )
    return system.solve()


def _no_slip_acceleration_errors(*, snapshot, unknowns) -> tuple[float, float]:
    """Return acceleration-level sticking residuals in the global belt direction."""

    geometry = snapshot.geometry
    state = snapshot.state
    primary = (
        unknowns.belt_acceleration
        - geometry.primary.effective * unknowns.primary_angular_acceleration
        - geometry.primary.d_effective_ds
        * state.shift_speed
        * state.primary_angular_speed
    )
    secondary = (
        unknowns.belt_acceleration
        - geometry.secondary.effective * unknowns.secondary_angular_acceleration
        - geometry.secondary.d_effective_ds
        * state.shift_speed
        * state.secondary_angular_speed
    )
    return primary, secondary


def _finite_difference_jacobian_determinant(
    *,
    primary_lambdas: np.ndarray,
    secondary_lambdas: np.ndarray,
    primary_residual: np.ndarray,
    secondary_residual: np.ndarray,
) -> np.ndarray:
    """Return det(d(Rp, Rs)/d(lambda_p, lambda_s)) on the sample grid."""

    if not (
        np.all(np.isfinite(primary_residual))
        and np.all(np.isfinite(secondary_residual))
    ):
        return np.full(primary_residual.shape, np.nan)

    # Array axis 0 is lambda_s and axis 1 is lambda_p.
    d_primary_d_lambda_s, d_primary_d_lambda_p = np.gradient(
        primary_residual,
        secondary_lambdas,
        primary_lambdas,
        edge_order=2,
    )
    d_secondary_d_lambda_s, d_secondary_d_lambda_p = np.gradient(
        secondary_residual,
        secondary_lambdas,
        primary_lambdas,
        edge_order=2,
    )
    return (
        d_primary_d_lambda_p * d_secondary_d_lambda_s
        - d_primary_d_lambda_s * d_secondary_d_lambda_p
    )


def _print_summary(
    *,
    scenario: str,
    state,
    snapshot,
    residual_map: LambdaResidualMap,
    base_samples: int,
    resolution_scale: float,
) -> None:
    print("\n" + "=" * 88)
    print(f"Scenario: {scenario}")
    print(
        "Convention: lambda_p and lambda_s are sampled over the positive "
        "forward-drive utilization domain."
    )
    print(
        "Grid: "
        f"base={base_samples}×{base_samples}, "
        f"resolution_scale={resolution_scale:g}, "
        f"effective={residual_map.primary_lambdas.size}×"
        f"{residual_map.secondary_lambdas.size}"
    )
    print(
        f"State: s={state.shift_position * 1_000.0:.4f} mm, "
        f"s_dot={state.shift_speed * 1_000.0:.4f} mm/s, "
        f"omega_s={state.secondary_angular_speed:.4f} rad/s"
    )
    print(
        f"Geometry: r_p={snapshot.geometry.primary.effective * 1_000.0:.4f} mm, "
        f"r_s={snapshot.geometry.secondary.effective * 1_000.0:.4f} mm"
    )

    finite = np.isfinite(residual_map.residual_norm)
    sampled = int(np.count_nonzero(finite))
    total = residual_map.residual_norm.size
    print(f"Solved grid points: {sampled}/{total}")
    if sampled:
        for name, values in (
            ("R_p", residual_map.primary_residual),
            ("R_s", residual_map.secondary_residual),
        ):
            finite_values = values[np.isfinite(values)]
            minimum = float(finite_values.min())
            maximum = float(finite_values.max())
            contains_zero = minimum <= 0.0 <= maximum
            print(
                f"  {name} range: {minimum:.6e} to {maximum:.6e} m/s^2 "
                f"(zero contour {'present' if contains_zero else 'absent'})"
            )
    if not sampled:
        print("No grid points produced a finite six-by-six trial solution.")
        return

    best_index = np.nanargmin(residual_map.residual_norm)
    secondary_index, primary_index = np.unravel_index(
        best_index,
        residual_map.residual_norm.shape,
    )
    lambda_primary = residual_map.primary_lambdas[primary_index]
    lambda_secondary = residual_map.secondary_lambdas[secondary_index]
    print("Best sampled point; this is not a root solve:")
    print(
        f"  lambda_p={lambda_primary:.6f}, lambda_s={lambda_secondary:.6f}, "
        f"||R||={residual_map.residual_norm[secondary_index, primary_index]:.6e} m/s^2"
    )
    print(
        f"  R_p={residual_map.primary_residual[secondary_index, primary_index]:.6e} m/s^2, "
        f"R_s={residual_map.secondary_residual[secondary_index, primary_index]:.6e} m/s^2"
    )
    print(
        f"  tau_p={residual_map.primary_torque[secondary_index, primary_index]:.6e} N m, "
        f"tau_s={residual_map.secondary_torque[secondary_index, primary_index]:.6e} N m"
    )
    print(
        f"  cond(A)={residual_map.condition_number[secondary_index, primary_index]:.6e}"
    )

    determinant = residual_map.determinant_jacobian
    finite_determinant = determinant[np.isfinite(determinant)]
    if finite_determinant.size:
        print(
            "Finite-difference Jacobian determinant range: "
            f"{finite_determinant.min():.6e} to {finite_determinant.max():.6e}"
        )
    finite_condition = residual_map.condition_number[
        np.isfinite(residual_map.condition_number)
    ]
    print(
        "Matrix condition-number range: "
        f"{finite_condition.min():.6e} to {finite_condition.max():.6e}"
    )


def plot_lambda_residual_map(
    *,
    scenario: str,
    residual_map: LambdaResidualMap,
    residual_linthresh: float,
    residual_clip_percentile: float,
    norm_clip_percentile: float,
    effective_samples: int,
):
    lambda_primary, lambda_secondary = np.meshgrid(
        residual_map.primary_lambdas,
        residual_map.secondary_lambdas,
        indexing="xy",
    )
    figure, axes = plt.subplots(2, 2, figsize=(16, 11), constrained_layout=True)
    ax_primary, ax_secondary, ax_overlay, ax_determinant = axes.flat

    _plot_signed_residual_field(
        axis=ax_primary,
        x=lambda_primary,
        y=lambda_secondary,
        values=residual_map.primary_residual,
        title=r"Primary no-slip residual $R_p$",
        colorbar_label=r"$R_p$ [m/s$^2$] (symmetric log scale)",
        residual_linthresh=residual_linthresh,
        clip_percentile=residual_clip_percentile,
        zero_color=_PRIMARY_ZERO_CONTOUR_COLOR,
    )
    _plot_signed_residual_field(
        axis=ax_secondary,
        x=lambda_primary,
        y=lambda_secondary,
        values=residual_map.secondary_residual,
        title=r"Secondary no-slip residual $R_s$",
        colorbar_label=r"$R_s$ [m/s$^2$] (symmetric log scale)",
        residual_linthresh=residual_linthresh,
        clip_percentile=residual_clip_percentile,
        zero_color=_SECONDARY_ZERO_CONTOUR_COLOR,
    )

    _plot_residual_norm_with_contours(
        axis=ax_overlay,
        x=lambda_primary,
        y=lambda_secondary,
        residual_map=residual_map,
        norm_clip_percentile=norm_clip_percentile,
    )

    _plot_signed_log_determinant(
        axis=ax_determinant,
        x=lambda_primary,
        y=lambda_secondary,
        determinant=residual_map.determinant_jacobian,
    )

    figure.suptitle(
        "CINDER stick-residual map: "
        f"{scenario} (positive lambda convention; {effective_samples}×"
        f"{effective_samples} grid)",
        fontsize=15,
    )
    return figure


def _plot_signed_residual_field(
    *,
    axis,
    x: np.ndarray,
    y: np.ndarray,
    values: np.ndarray,
    title: str,
    colorbar_label: str,
    residual_linthresh: float,
    clip_percentile: float,
    zero_color: str,
) -> None:
    limit = _robust_absolute_limit(values, percentile=clip_percentile)
    limit = max(limit, residual_linthresh * 2.0)
    norm = SymLogNorm(
        linthresh=residual_linthresh,
        linscale=1.0,
        vmin=-limit,
        vmax=limit,
        base=10.0,
    )
    plot = axis.contourf(
        x,
        y,
        np.ma.masked_invalid(values),
        levels=_symmetric_symlog_levels(
            limit=limit,
            linthresh=residual_linthresh,
        ),
        cmap="RdBu_r",
        norm=norm,
        extend="both",
    )
    axis.figure.colorbar(plot, ax=axis, label=colorbar_label, extend="both")
    _draw_zero_contour(
        axis=axis,
        x=x,
        y=y,
        values=values,
        color=zero_color,
        linestyle="solid",
        label=r"$R=0$",
    )
    axis.set_title(title)
    _format_lambda_axis(axis)


def _plot_residual_norm_with_contours(
    *,
    axis,
    x: np.ndarray,
    y: np.ndarray,
    residual_map: LambdaResidualMap,
    norm_clip_percentile: float,
) -> None:
    residual_norm = residual_map.residual_norm
    vmin, vmax = _positive_log_limits(
        residual_norm,
        percentile=norm_clip_percentile,
    )
    norm = LogNorm(vmin=vmin, vmax=vmax)
    plot = axis.contourf(
        x,
        y,
        np.ma.masked_invalid(residual_norm),
        levels=np.geomspace(vmin, vmax, 42),
        cmap="magma_r",
        norm=norm,
        extend="max",
    )
    axis.figure.colorbar(
        plot,
        ax=axis,
        label=r"$\sqrt{R_p^2 + R_s^2}$ [m/s$^2$] (log scale)",
        extend="max",
    )

    _draw_zero_contour(
        axis=axis,
        x=x,
        y=y,
        values=residual_map.primary_residual,
        color=_PRIMARY_ZERO_CONTOUR_COLOR,
        linestyle="solid",
        label=r"$R_p=0$",
    )
    _draw_zero_contour(
        axis=axis,
        x=x,
        y=y,
        values=residual_map.secondary_residual,
        color=_SECONDARY_ZERO_CONTOUR_COLOR,
        linestyle="dashed",
        label=r"$R_s=0$",
    )

    best_secondary_index, best_primary_index = np.unravel_index(
        np.nanargmin(residual_norm),
        residual_norm.shape,
    )
    axis.plot(
        residual_map.primary_lambdas[best_primary_index],
        residual_map.secondary_lambdas[best_secondary_index],
        marker="x",
        markersize=8.0,
        markeredgewidth=2.2,
        color="white",
        markeredgecolor="black",
        linestyle="None",
        zorder=5,
    )

    legend_handles = (
        Line2D(
            [],
            [],
            color=_PRIMARY_ZERO_CONTOUR_COLOR,
            linewidth=2.6,
            label=r"$R_p=0$",
        ),
        Line2D(
            [],
            [],
            color=_SECONDARY_ZERO_CONTOUR_COLOR,
            linewidth=2.6,
            linestyle="--",
            label=r"$R_s=0$",
        ),
        Line2D(
            [],
            [],
            color="white",
            marker="x",
            markeredgecolor="black",
            markersize=8.0,
            markeredgewidth=2.0,
            linestyle="None",
            label="best sampled point",
        ),
    )
    axis.legend(handles=legend_handles, loc="best", framealpha=0.92)
    axis.set_title(r"Residual norm with explicit zero contours")
    _format_lambda_axis(axis)


def _plot_signed_log_determinant(*, axis, x, y, determinant: np.ndarray) -> None:
    signed_log_determinant = np.sign(determinant) * np.log10(
        1.0 + np.abs(determinant)
    )
    limit = _robust_absolute_limit(signed_log_determinant, percentile=99.0)
    limit = max(limit, 1.0)
    plot = axis.contourf(
        x,
        y,
        np.ma.masked_invalid(signed_log_determinant),
        levels=np.linspace(-limit, limit, 61),
        cmap="PiYG",
        norm=TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit),
        extend="both",
    )
    axis.figure.colorbar(
        plot,
        ax=axis,
        label=r"sign(det J) log$_{10}$(1 + |det J|)",
        extend="both",
    )
    axis.set_title(r"Signed log Jacobian determinant")
    _format_lambda_axis(axis)


def _draw_zero_contour(
    *,
    axis,
    x: np.ndarray,
    y: np.ndarray,
    values: np.ndarray,
    color: str,
    linestyle: str,
    label: str,
) -> None:
    finite_values = values[np.isfinite(values)]
    if not finite_values.size or not (finite_values.min() <= 0.0 <= finite_values.max()):
        return

    masked_values = np.ma.masked_invalid(values)
    # Black underlay keeps the contour readable against both light and dark
    # portions of the selected field colormap.
    axis.contour(
        x,
        y,
        masked_values,
        levels=(0.0,),
        colors="black",
        linestyles=linestyle,
        linewidths=4.2,
        zorder=4,
    )
    axis.contour(
        x,
        y,
        masked_values,
        levels=(0.0,),
        colors=color,
        linestyles=linestyle,
        linewidths=2.35,
        zorder=5,
    )


def _symmetric_symlog_levels(
    *,
    limit: float,
    linthresh: float,
) -> np.ndarray:
    """Return smooth contour levels that retain resolution near zero."""

    linear_half_width = min(linthresh, limit)
    linear = np.linspace(-linear_half_width, linear_half_width, 17)
    if limit <= linear_half_width:
        return linear

    positive = np.geomspace(linear_half_width, limit, 28)
    levels = np.concatenate((-positive[::-1], linear, positive))
    return np.unique(levels)


def _robust_absolute_limit(values: np.ndarray, *, percentile: float) -> float:
    finite_values = np.abs(values[np.isfinite(values)])
    if not finite_values.size:
        return 1.0
    return float(np.percentile(finite_values, percentile))


def _positive_log_limits(values: np.ndarray, *, percentile: float) -> tuple[float, float]:
    finite_positive = values[np.isfinite(values) & (values > 0.0)]
    if not finite_positive.size:
        return 1e-6, 1.0
    vmin = max(float(np.percentile(finite_positive, 1.0)), 1e-8)
    vmax = float(np.percentile(finite_positive, percentile))
    if vmax <= vmin:
        vmax = vmin * 10.0
    return vmin, vmax


def _format_lambda_axis(axis) -> None:
    axis.set_xlabel(r"$\lambda_p$ [-]")
    axis.set_ylabel(r"$\lambda_s$ [-]")
    axis.grid(True, alpha=0.25)


if __name__ == "__main__":
    main()
