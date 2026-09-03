"""Audit the source-constrained Ballew (2015) primary-speed controller mapping.

Ballew publishes Kff=1.2, Kp=5, Ki=75 and a 2500 rpm speed objective, but not
an executable controller equation. Figure 41 (primary RPM) and Figure 45
(primary clamp force) provide a consistency check on the dynamic PI term without
fitting any gain used by the benchmark.

The diagnostic least-squares values written by this script are *not* fed back
into ``run.py``. They exist only to document why Reconstruction A11 chooses RPM
error with the sign ``primary_rpm - target_rpm``.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from math import pi, sqrt
from pathlib import Path
import subprocess
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from numpy.typing import NDArray  # noqa: E402

import cinder  # noqa: E402

from benchmark.constants import (  # noqa: E402
    PUBLISHED,
    RECONSTRUCTED_CONTROLLER_FEED_FORWARD_FORCE_N,
)
from benchmark.reference import load_series, validate_reference_data  # noqa: E402

STUDY_ROOT = Path(__file__).resolve().parent
RELEASE_ROOT = STUDY_ROOT.parents[1]
VERIFY_ENVIRONMENT = RELEASE_ROOT / "verify_environment.py"
VERIFY_STUDY = STUDY_ROOT / "verify_study.py"
REFERENCE = STUDY_ROOT / "reference"
DEFAULT_OUTPUT_DIR = STUDY_ROOT / "artifacts" / "controller-reconstruction"
EXPECTED_CINDER_VERSION = "1.0.0"
RAD_PER_S_PER_RPM = 2.0 * pi / 60.0


@dataclass(frozen=True, slots=True)
class ShapeCheck:
    error_definition: str
    error_units: str
    count: int
    rmse_n: float
    mae_n: float
    mean_error_n: float
    max_abs_error_n: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--no-plot", action="store_true")
    return parser.parse_args()


def _cumtrap(
    values: NDArray[np.float64],
    times: NDArray[np.float64],
) -> NDArray[np.float64]:
    result = np.zeros_like(values)
    result[1:] = np.cumsum(
        0.5 * (values[1:] + values[:-1]) * np.diff(times)
    )
    return result


def _visible_overlap(input_rpm, primary_force):
    # prepare_reference_data.py inserts a synthetic t=0 hold for force replay.
    # The second force point is the first actually digitized Figure 45 point.
    if primary_force.time_s.size < 2 or primary_force.time_s[0] != 0.0:
        raise RuntimeError(
            "Expected prepared Figure 45 force to contain the A6 t=0 hold."
        )
    first_visible_force_time = float(primary_force.time_s[1])
    start = max(first_visible_force_time, float(input_rpm.time_s[0]))
    end = min(float(primary_force.time_s[-1]), float(input_rpm.time_s[-1]))
    mask = (primary_force.time_s >= start) & (primary_force.time_s <= end)
    times = primary_force.time_s[mask]
    force = primary_force.value[mask]
    rpm = np.interp(times, input_rpm.time_s, input_rpm.value)
    return times, rpm, force


def _shape_check(
    *,
    times: NDArray[np.float64],
    rpm: NDArray[np.float64],
    force: NDArray[np.float64],
    measured_minus_target: bool,
    use_rpm_units: bool,
) -> tuple[ShapeCheck, NDArray[np.float64]]:
    sign = 1.0 if measured_minus_target else -1.0
    scale = 1.0 if use_rpm_units else RAD_PER_S_PER_RPM
    error = sign * (rpm - PUBLISHED.initial_input_rpm) * scale
    integral = _cumtrap(error, times)

    predicted_delta = (
        PUBLISHED.proportional_gain * (error - error[0])
        + PUBLISHED.integral_gain * integral
    )
    observed_delta = force - force[0]
    residual = predicted_delta - observed_delta
    rmse = sqrt(float(np.mean(residual**2)))
    check = ShapeCheck(
        error_definition=(
            "measured_minus_target"
            if measured_minus_target
            else "target_minus_measured"
        ),
        error_units="rpm" if use_rpm_units else "rad_per_s",
        count=int(times.size),
        rmse_n=rmse,
        mae_n=float(np.mean(np.abs(residual))),
        mean_error_n=float(np.mean(residual)),
        max_abs_error_n=float(np.max(np.abs(residual))),
    )
    return check, predicted_delta


def analyse_controller_reconstruction():
    reference_dir = validate_reference_data(study_root=STUDY_ROOT)
    input_rpm = load_series(
        reference_dir / "figure_41_input_rpm.csv",
        value_column="input_rpm",
    )
    force = load_series(
        reference_dir / "figure_45_primary_force.csv",
        value_column="primary_axial_force_n",
    )
    times, rpm, force_values = _visible_overlap(input_rpm, force)

    checks: list[ShapeCheck] = []
    predictions: dict[str, NDArray[np.float64]] = {}
    for measured_minus_target in (True, False):
        for use_rpm_units in (True, False):
            check, predicted = _shape_check(
                times=times,
                rpm=rpm,
                force=force_values,
                measured_minus_target=measured_minus_target,
                use_rpm_units=use_rpm_units,
            )
            checks.append(check)
            predictions[
                f"{check.error_definition}__{check.error_units}"
            ] = predicted

    # Diagnostic only: these fitted values are never used by the benchmark.
    error_rpm = rpm - PUBLISHED.initial_input_rpm
    integral_rpm_s = _cumtrap(error_rpm, times)
    design = np.column_stack((error_rpm - error_rpm[0], integral_rpm_s))
    fitted_kp, fitted_ki = np.linalg.lstsq(
        design,
        force_values - force_values[0],
        rcond=None,
    )[0]
    residual_with_published_kp = (
        force_values
        - force_values[0]
        - PUBLISHED.proportional_gain * (error_rpm - error_rpm[0])
    )
    fitted_ki_with_published_kp = float(
        integral_rpm_s @ residual_with_published_kp
        / (integral_rpm_s @ integral_rpm_s)
    )

    payload = {
        "source_published": {
            "target_primary_rpm": PUBLISHED.initial_input_rpm,
            "feed_forward_gain": PUBLISHED.feed_forward_gain,
            "proportional_gain": PUBLISHED.proportional_gain,
            "integral_gain": PUBLISHED.integral_gain,
            "fixed_secondary_clamp_n": PUBLISHED.output_axial_force_n,
        },
        "source_missing": [
            "explicit controller algebraic equation",
            "quantity multiplied by the dimensionless feed-forward gain",
            "initial integral state / controller bias",
            "output saturation or anti-windup implementation",
        ],
        "headline_reconstruction": {
            "error_definition": "primary_rpm - target_rpm",
            "error_units": "rpm",
            "feed_forward_interpretation": "Kff * fixed_secondary_clamp",
            "feed_forward_force_n": (
                RECONSTRUCTED_CONTROLLER_FEED_FORWARD_FORCE_N
            ),
            "initial_error_integral_rpm_s": 0.0,
            "saturation_or_anti_windup": "none added; not published",
            "equation": (
                "Fp = Kff*Fs + Kp*(np-target) + "
                "Ki*integral(np-target)dt"
            ),
            "status": (
                "source-constrained reconstruction; no fitted values are used "
                "by the benchmark controller"
            ),
        },
        "digitized_shape_consistency": {
            "method": (
                "Compare Figure 45 force changes against published PI gains "
                "over the common visible Figure 41/45 interval. Anchoring at "
                "the first common time cancels any constant feed-forward term "
                "and pre-existing controller bias."
            ),
            "common_start_s": float(times[0]),
            "common_end_s": float(times[-1]),
            "checks": [asdict(check) for check in checks],
            "best_supported_candidate": "measured_minus_target__rpm",
            "diagnostic_fit_not_used_by_controller": {
                "least_squares_kp": float(fitted_kp),
                "least_squares_ki": float(fitted_ki),
                "ki_with_kp_fixed_at_published_5": (
                    fitted_ki_with_published_kp
                ),
            },
        },
    }
    arrays = {
        "time_s": times,
        "observed_delta_force_n": force_values - force_values[0],
        **predictions,
    }
    return payload, arrays


def main() -> int:
    args = parse_args()
    subprocess.run([sys.executable, str(VERIFY_ENVIRONMENT)], check=True)
    subprocess.run([sys.executable, str(VERIFY_STUDY)], check=True)
    if cinder.__version__ != EXPECTED_CINDER_VERSION:
        raise SystemExit(
            f"Expected CINDER {EXPECTED_CINDER_VERSION}, found {cinder.__version__}."
        )

    payload, arrays = analyse_controller_reconstruction()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "controller_reconstruction.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    if not args.no_plot:
        fig, ax = plt.subplots(figsize=(9.0, 5.2))
        ax.plot(
            arrays["time_s"],
            arrays["observed_delta_force_n"],
            label="Figure 45 force change",
        )
        ax.plot(
            arrays["time_s"],
            arrays["measured_minus_target__rpm"],
            label="Published PI gains; e = RPM - 2500",
        )
        ax.plot(
            arrays["time_s"],
            arrays["measured_minus_target__rad_per_s"],
            linestyle="--",
            label="Same gains interpreted on rad/s error",
        )
        ax.set_xlabel("Time [s]")
        ax.set_ylabel("Force change from first common point [N]")
        ax.set_title(
            "Ballew controller reconstruction: offset-free PI consistency check"
        )
        ax.grid(True, alpha=0.25)
        ax.legend()
        fig.tight_layout()
        fig.savefig(args.output_dir / "controller_shape_check.png", dpi=180)
        plt.close(fig)

    print(f"Artifacts: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
