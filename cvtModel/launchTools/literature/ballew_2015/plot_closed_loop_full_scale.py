"""Plot the Ballew closed-loop comparison on zero-anchored, case-scale axes.

The canonical ``closed_loop_comparison.png`` autoscales each panel, which is useful
for inspecting residual shape but visually magnifies small speed/ratio differences.
This companion figure uses the same comparison CSVs and the same traces, but anchors
every y-axis at zero and rounds the upper bound above the largest displayed value.
"""

from __future__ import annotations

import argparse
from math import ceil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parent
DEFAULT_RESULTS_DIR = ROOT / "results" / "closed_loop"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot the closed-loop Ballew comparison with zero-anchored y-axes."
    )
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output PNG. Defaults to <results-dir>/closed_loop_comparison_full_scale.png.",
    )
    return parser.parse_args()


def _load(path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Run run_closed_loop_comparison.py first "
            "(and ensure Git LFS outputs are present)."
        )
    return np.genfromtxt(path, delimiter=",", names=True, dtype=float)


def _zero_anchored_upper(*series: np.ndarray, step: float, headroom: float = 1.08) -> float:
    values = np.concatenate([np.asarray(s, dtype=float).reshape(-1) for s in series])
    values = values[np.isfinite(values)]
    if values.size == 0:
        return step
    maximum = max(0.0, float(np.max(values)))
    return max(step, ceil((maximum * headroom) / step) * step)


def main() -> None:
    args = parse_args()
    results = args.results_dir.resolve()
    output = (
        args.output.resolve()
        if args.output is not None
        else results / "closed_loop_comparison_full_scale.png"
    )

    primary = _load(results / "input_rpm_comparison.csv")
    secondary = _load(results / "output_rpm_comparison.csv")
    ratio = _load(results / "ratio_comparison.csv")
    force = _load(results / "primary_force_comparison.csv")

    fig, axes = plt.subplots(4, 1, figsize=(9.0, 10.5), sharex=True)

    axes[0].scatter(
        primary["time_s"], primary["ballew_input_rpm"], s=12, label="Ballew primary"
    )
    axes[0].plot(
        primary["time_s"], primary["cinder_primary_rpm"], label="CINDER primary"
    )
    axes[0].set_ylabel("Primary RPM")
    axes[0].set_ylim(
        0.0,
        _zero_anchored_upper(
            primary["ballew_input_rpm"], primary["cinder_primary_rpm"], step=500.0
        ),
    )
    axes[0].legend()
    axes[0].grid(True, alpha=0.25)

    axes[1].scatter(
        secondary["time_s"], secondary["ballew_output_rpm"],
        s=12, label="Ballew secondary"
    )
    axes[1].plot(
        secondary["time_s"], secondary["cinder_secondary_rpm"],
        label="CINDER secondary"
    )
    axes[1].set_ylabel("Secondary RPM")
    axes[1].set_ylim(
        0.0,
        _zero_anchored_upper(
            secondary["ballew_output_rpm"],
            secondary["cinder_secondary_rpm"],
            step=500.0,
        ),
    )
    axes[1].legend()
    axes[1].grid(True, alpha=0.25)

    axes[2].scatter(
        ratio["time_s"], ratio["ballew_speed_ratio"], s=10, label="Ballew ratio"
    )
    axes[2].plot(
        ratio["time_s"], ratio["cinder_speed_ratio"], label="CINDER ratio"
    )
    axes[2].set_ylabel(r"$\omega_p/\omega_s$")
    axes[2].set_ylim(
        0.0,
        _zero_anchored_upper(
            ratio["ballew_speed_ratio"], ratio["cinder_speed_ratio"], step=0.5
        ),
    )
    axes[2].legend()
    axes[2].grid(True, alpha=0.25)

    axes[3].scatter(
        force["time_s"], force["ballew_primary_force_n"],
        s=10, label="Ballew Figure 45"
    )
    axes[3].plot(
        force["time_s"], force["cinder_controller_force_n"],
        label="CINDER controller output"
    )
    axes[3].set_ylabel("Primary clamp [N]")
    axes[3].set_xlabel("Time [s]")
    axes[3].set_ylim(
        0.0,
        _zero_anchored_upper(
            force["ballew_primary_force_n"],
            force["cinder_controller_force_n"],
            step=500.0,
        ),
    )
    axes[3].legend()
    axes[3].grid(True, alpha=0.25)

    all_times = np.concatenate(
        [primary["time_s"], secondary["time_s"], ratio["time_s"], force["time_s"]]
    )
    finite_times = all_times[np.isfinite(all_times)]
    if finite_times.size:
        axes[3].set_xlim(0.0, max(0.0, float(np.max(finite_times))))

    fig.suptitle("Closed-loop Ballew controller comparison — full variable scale")
    fig.text(
        0.5,
        0.006,
        "Y-axes anchored at zero with rounded case-scale ceilings; "
        "closed_loop_comparison.png remains the magnified residual view.",
        ha="center",
        va="bottom",
        fontsize=8,
    )
    fig.tight_layout(rect=(0.0, 0.025, 1.0, 0.98))
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=220)
    plt.close(fig)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
