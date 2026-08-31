"""Comparison metrics and compact figures for the Ballew benchmark."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from math import sqrt
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .reference import ReferenceSeries


@dataclass(frozen=True, slots=True)
class ErrorMetrics:
    count: int
    mean_error: float
    mean_absolute_error: float
    root_mean_square_error: float
    max_absolute_error: float
    rmse_percent_of_reference_mean: float


def compute_error_metrics(
    *, reference: Sequence[float], predicted: Sequence[float]
) -> ErrorMetrics:
    ref = np.asarray(reference, dtype=float)
    pred = np.asarray(predicted, dtype=float)
    if ref.shape != pred.shape or ref.ndim != 1 or ref.size == 0:
        raise ValueError("reference and predicted must be aligned non-empty vectors.")
    if not np.all(np.isfinite(ref)) or not np.all(np.isfinite(pred)):
        raise ValueError("reference and predicted values must be finite.")
    error = pred - ref
    rmse = sqrt(float(np.mean(error**2)))
    reference_mean = float(np.mean(np.abs(ref)))
    return ErrorMetrics(
        count=int(ref.size),
        mean_error=float(np.mean(error)),
        mean_absolute_error=float(np.mean(np.abs(error))),
        root_mean_square_error=rmse,
        max_absolute_error=float(np.max(np.abs(error))),
        rmse_percent_of_reference_mean=(
            100.0 * rmse / reference_mean if reference_mean > 0.0 else float("nan")
        ),
    )


def metric_document(metric: ErrorMetrics) -> dict[str, object]:
    return asdict(metric)


def write_comparison_csv(
    path: Path,
    *,
    time_s,
    reference,
    predicted,
    reference_name: str,
    predicted_name: str,
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("time_s", reference_name, predicted_name, "error"))
        for time, ref, pred in zip(time_s, reference, predicted, strict=True):
            writer.writerow((time, ref, pred, pred - ref))


def plot_protocol(
    path: Path,
    *,
    protocol_name: str,
    input_ref: ReferenceSeries,
    input_pred,
    output_ref: ReferenceSeries,
    output_pred,
    ratio_ref: ReferenceSeries,
    ratio_pred,
    force_ref: ReferenceSeries,
    force_pred=None,
) -> None:
    fig, axes = plt.subplots(4, 1, figsize=(9.0, 10.0), sharex=False)

    axes[0].plot(input_ref.time_s, input_ref.value, label="Ballew")
    axes[0].plot(input_ref.time_s, input_pred, label="CINDER")
    axes[0].set_ylabel("Primary rpm")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend()

    axes[1].plot(output_ref.time_s, output_ref.value, label="Ballew")
    axes[1].plot(output_ref.time_s, output_pred, label="CINDER")
    axes[1].set_ylabel("Secondary rpm")
    axes[1].grid(True, alpha=0.25)
    axes[1].legend()

    axes[2].plot(ratio_ref.time_s, ratio_ref.value, label="Ballew")
    axes[2].plot(ratio_ref.time_s, ratio_pred, label="CINDER")
    axes[2].set_ylabel("Speed ratio")
    axes[2].grid(True, alpha=0.25)
    axes[2].legend()

    axes[3].plot(force_ref.time_s, force_ref.value, label="Ballew Figure 45")
    if force_pred is not None:
        axes[3].plot(force_ref.time_s[1:], force_pred, label="CINDER controller")
    axes[3].set_ylabel("Primary clamp (N)")
    axes[3].set_xlabel("Time (s)")
    axes[3].grid(True, alpha=0.25)
    axes[3].legend()

    fig.suptitle(protocol_name)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


HISTORICAL_V1_0_0 = {
    "force_replay": {
        "primary_rpm_rmse": 1796.1055474843045,
        "secondary_rpm_rmse": 38.2552150912746,
        "speed_ratio_rmse": 1.4513405346478947,
        "transition_count": 251,
    },
    "closed_loop": {
        "primary_rpm_rmse": 109.66510967962864,
        "secondary_rpm_rmse": 32.92155449116345,
        "speed_ratio_rmse": 0.10929942366273752,
        "primary_force_rmse_n": 1180.2275546433493,
        "transition_count": 1629,
    },
}


def historical_regression(
    *, protocol: str, metrics: dict[str, object], transition_count: int
) -> dict[str, object]:
    expected = HISTORICAL_V1_0_0[protocol]
    actual = {
        "primary_rpm_rmse": metrics["primary_rpm"]["root_mean_square_error"],
        "secondary_rpm_rmse": metrics["secondary_rpm"]["root_mean_square_error"],
        "speed_ratio_rmse": metrics["speed_ratio"]["root_mean_square_error"],
        "transition_count": transition_count,
    }
    if protocol == "closed_loop":
        actual["primary_force_rmse_n"] = metrics["primary_force"][
            "root_mean_square_error"
        ]

    comparison: dict[str, object] = {}
    for key, expected_value in expected.items():
        actual_value = actual[key]
        if isinstance(expected_value, int):
            comparison[key] = {
                "historical": expected_value,
                "rerun": actual_value,
                "delta": int(actual_value) - expected_value,
                "note": "raw hybrid transition count can be tolerance-sensitive",
            }
        else:
            comparison[key] = {
                "historical": expected_value,
                "rerun": actual_value,
                "absolute_delta": float(actual_value) - expected_value,
                "relative_delta_percent": 100.0
                * (float(actual_value) - expected_value)
                / expected_value,
            }
    return comparison
