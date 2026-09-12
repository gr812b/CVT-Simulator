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


def plot_protocol_full_scale(
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
    """Plot the same comparison with every y-axis anchored at zero.

    The ordinary comparison intentionally autoscales so residual shape is easy
    to inspect. This companion view prevents that autoscaling from visually
    exaggerating small relative differences in the closed-loop case.
    """

    def upper(*series, step: float, headroom: float = 1.08) -> float:
        values = np.concatenate(
            [np.asarray(item, dtype=float).reshape(-1) for item in series]
        )
        values = values[np.isfinite(values)]
        if not values.size:
            return step
        maximum = max(0.0, float(np.max(values))) * headroom
        return max(step, float(np.ceil(maximum / step) * step))

    fig, axes = plt.subplots(4, 1, figsize=(9.0, 10.5), sharex=False)

    axes[0].plot(input_ref.time_s, input_ref.value, label="Ballew")
    axes[0].plot(input_ref.time_s, input_pred, label="CINDER")
    axes[0].set_ylabel("Primary rpm")
    axes[0].set_ylim(0.0, upper(input_ref.value, input_pred, step=500.0))
    axes[0].grid(True, alpha=0.25)
    axes[0].legend()

    axes[1].plot(output_ref.time_s, output_ref.value, label="Ballew")
    axes[1].plot(output_ref.time_s, output_pred, label="CINDER")
    axes[1].set_ylabel("Secondary rpm")
    axes[1].set_ylim(0.0, upper(output_ref.value, output_pred, step=500.0))
    axes[1].grid(True, alpha=0.25)
    axes[1].legend()

    axes[2].plot(ratio_ref.time_s, ratio_ref.value, label="Ballew")
    axes[2].plot(ratio_ref.time_s, ratio_pred, label="CINDER")
    axes[2].set_ylabel("Speed ratio")
    axes[2].set_ylim(0.0, upper(ratio_ref.value, ratio_pred, step=0.5))
    axes[2].grid(True, alpha=0.25)
    axes[2].legend()

    axes[3].plot(force_ref.time_s, force_ref.value, label="Ballew Figure 45")
    force_for_scale = [force_ref.value]
    if force_pred is not None:
        axes[3].plot(
            force_ref.time_s[1:],
            force_pred,
            label="CINDER controller",
        )
        force_for_scale.append(force_pred)
    axes[3].set_ylabel("Primary clamp [N]")
    axes[3].set_xlabel("Time [s]")
    axes[3].set_ylim(0.0, upper(*force_for_scale, step=500.0))
    axes[3].grid(True, alpha=0.25)
    axes[3].legend()

    fig.suptitle(protocol_name + " — full scale")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
