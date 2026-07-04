"""Map stick residuals over a deliberately wide signed lambda domain.

This is an algebraic diagnostic companion to ``preview_lambda_residual_map.py``.
It freezes the same snapshot and evaluates the same normal-resultant closure,
but samples

    (lambda_p, lambda_s) in [-10, 10] x [-10, 10]

by default.  The purpose is to see whether the two acceleration-level stick
residual contours intersect anywhere in a broad continuation of the current
equations.

Negative lambda values are *not* a physical forward-drive Coulomb-contact
state under the present sign convention.  They are included only to reveal the
structure of the provisional algebraic closure and to distinguish "no root in
the physical quadrant" from "no nearby root at all."

Run from the repository root:

    python tools/preview_lambda_residual_wide_map.py
    python tools/preview_lambda_residual_wide_map.py --scenario active-shift
    python tools/preview_lambda_residual_wide_map.py --samples 401 \
        --save artifacts/lambda_wide_map.png --no-show
"""

from __future__ import annotations

import argparse
from math import isfinite
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np

# Support both the normal src/cinder repository layout and direct overlays.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (_REPOSITORY_ROOT / "src", _REPOSITORY_ROOT):
    if (_candidate / "cinder").is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from baja_trial_baseline import build_baja_trial_baseline
from cinder.dynamics import build_state_fixed_equations
from preview_lambda_residual_map import (
    _scaled_sample_count,
    _select_state,
    build_lambda_residual_map,
    plot_lambda_residual_map,
)

DEFAULT_LAMBDA_MIN = -20
DEFAULT_LAMBDA_MAX = 20
DEFAULT_SAMPLES = 1001
DEFAULT_RESIDUAL_LINTHRESH = 1.0
DEFAULT_RESIDUAL_CLIP_PERCENTILE = 99.0
DEFAULT_NORM_CLIP_PERCENTILE = 99.5


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Map normal-resultant stick residuals over a wide signed "
            "lambda_p/lambda_s diagnostic domain."
        )
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
        default=DEFAULT_LAMBDA_MIN,
        help="Smallest signed lambda sampled.",
    )
    parser.add_argument(
        "--lambda-max",
        type=float,
        default=DEFAULT_LAMBDA_MAX,
        help="Largest signed lambda sampled.",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=DEFAULT_SAMPLES,
        help="Grid points per lambda direction before resolution scaling.",
    )
    parser.add_argument(
        "--resolution-scale",
        type=float,
        default=1.0,
        help="Multiplier applied to the number of sampled intervals per direction.",
    )
    parser.add_argument(
        "--residual-linthresh",
        type=float,
        default=DEFAULT_RESIDUAL_LINTHRESH,
        help="Half-width of the signed-residual linear colour band [m/s^2].",
    )
    parser.add_argument(
        "--residual-clip-percentile",
        type=float,
        default=DEFAULT_RESIDUAL_CLIP_PERCENTILE,
        help="Robust percentile saturation for signed residual fields.",
    )
    parser.add_argument(
        "--norm-clip-percentile",
        type=float,
        default=DEFAULT_NORM_CLIP_PERCENTILE,
        help="Robust percentile saturation for the residual-norm field.",
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

    if not isfinite(args.lambda_min):
        parser.error("--lambda-min must be finite.")
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
    _print_wide_summary(
        scenario=args.scenario,
        lambda_min=args.lambda_min,
        lambda_max=args.lambda_max,
        effective_samples=effective_samples,
        residual_map=residual_map,
    )

    figure = plot_lambda_residual_map(
        scenario=args.scenario,
        residual_map=residual_map,
        residual_linthresh=args.residual_linthresh,
        residual_clip_percentile=args.residual_clip_percentile,
        norm_clip_percentile=args.norm_clip_percentile,
        effective_samples=effective_samples,
    )
    figure.suptitle(
        "CINDER wide signed-lambda diagnostic map: "
        f"{args.scenario} ({effective_samples}×{effective_samples} grid)",
        fontsize=15,
    )

    if args.save is not None:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(args.save, dpi=180)
        print(f"Saved {args.save}")
    if not args.no_show:
        plt.show()


def _print_wide_summary(
    *,
    scenario: str,
    lambda_min: float,
    lambda_max: float,
    effective_samples: int,
    residual_map,
) -> None:
    """Print only diagnostics that remain meaningful for signed continuation."""

    print("\n" + "=" * 88)
    print(f"Scenario: {scenario}")
    print(
        "Diagnostic convention: signed lambdas are sampled algebraically; "
        "negative values are not physical forward-drive contact states."
    )
    print(
        "Grid: "
        f"{effective_samples}×{effective_samples}, "
        f"lambda_p, lambda_s in [{lambda_min:g}, {lambda_max:g}]"
    )

    finite = np.isfinite(residual_map.residual_norm)
    solved = int(np.count_nonzero(finite))
    total = residual_map.residual_norm.size
    print(f"Solved grid points: {solved}/{total}")
    if not solved:
        return

    for name, values in (
        ("R_p", residual_map.primary_residual),
        ("R_s", residual_map.secondary_residual),
    ):
        finite_values = values[np.isfinite(values)]
        minimum = float(finite_values.min())
        maximum = float(finite_values.max())
        contour_present = minimum <= 0.0 <= maximum
        print(
            f"  {name} range: {minimum:.6e} to {maximum:.6e} m/s^2 "
            f"(zero contour {'present' if contour_present else 'absent'})"
        )

    best_index = np.nanargmin(residual_map.residual_norm)
    secondary_index, primary_index = np.unravel_index(
        best_index,
        residual_map.residual_norm.shape,
    )
    print("Best sampled point; this is not a root solve:")
    print(
        "  "
        f"lambda_p={residual_map.primary_lambdas[primary_index]:.8g}, "
        f"lambda_s={residual_map.secondary_lambdas[secondary_index]:.8g}, "
        f"||R||={residual_map.residual_norm[secondary_index, primary_index]:.6e} m/s^2"
    )
    print(
        "  "
        f"R_p={residual_map.primary_residual[secondary_index, primary_index]:.6e} m/s^2, "
        f"R_s={residual_map.secondary_residual[secondary_index, primary_index]:.6e} m/s^2"
    )
    print(
        "  "
        f"tau_p={residual_map.primary_torque[secondary_index, primary_index]:.6e} N m, "
        f"tau_s={residual_map.secondary_torque[secondary_index, primary_index]:.6e} N m"
    )
    print(
        "  "
        f"N_p={residual_map.primary_normal_resultant[secondary_index, primary_index]:.6e} N, "
        f"N_s={residual_map.secondary_normal_resultant[secondary_index, primary_index]:.6e} N"
    )

    finite_condition = residual_map.condition_number[
        np.isfinite(residual_map.condition_number)
    ]
    if finite_condition.size:
        print(
            "Condition-number range: "
            f"{finite_condition.min():.6e} to {finite_condition.max():.6e}"
        )


if __name__ == "__main__":
    main()
