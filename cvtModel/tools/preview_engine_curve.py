# tools/preview_engine_curve.py

from __future__ import annotations

import argparse
from math import pi

import matplotlib.pyplot as plt
import numpy as np

from cinder.engine import (
    EngineTorquePoint,
    FullThrottleTorqueCurve,
    TorqueCurveSpec,
)


_RPM_TO_RAD_PER_SECOND = 2.0 * pi / 60.0
_FOOT_POUND_FORCE_TO_NEWTON_METER = 1.3558179483314004


# Legacy full-throttle dyno-style measurements. Unit conversion stays in this
# preview tool; the CINDER engine package itself accepts SI only.
_BRIGGS_WOT_POINTS_RPM_FT_LBF = (
    (1000.0, 0.0),
    (1800.0, 18.0),
    (2400.0, 18.5),
    (2600.0, 18.1),
    (2800.0, 17.4),
    (3000.0, 16.6),
    (3200.0, 15.4),
    (3400.0, 14.5),
    (3600.0, 13.5),
    (4000.0, 0.0),
)


def rpm_to_rad_per_second(rpm: float) -> float:
    return rpm * _RPM_TO_RAD_PER_SECOND


def foot_pound_force_to_newton_meter(torque: float) -> float:
    return torque * _FOOT_POUND_FORCE_TO_NEWTON_METER


def build_torque_curve() -> FullThrottleTorqueCurve:
    points = tuple(
        EngineTorquePoint(
            angular_speed=rpm_to_rad_per_second(rpm),
            torque=foot_pound_force_to_newton_meter(torque),
        )
        for rpm, torque in _BRIGGS_WOT_POINTS_RPM_FT_LBF
    )

    return FullThrottleTorqueCurve(
        TorqueCurveSpec(
            points=points,
            low_speed_braking_torque=-4.0,
            low_speed_braking_peak_speed=rpm_to_rad_per_second(700.0),
            high_speed_braking_torque=-4.0,
            high_speed_braking_transition_width=rpm_to_rad_per_second(400.0),
        )
    )


def align_zero_levels(
    *,
    reference_axis: plt.Axes,
    target_axis: plt.Axes,
    target_values: np.ndarray,
) -> None:
    """Align the displayed zero levels of two twinned vertical axes."""

    reference_minimum, reference_maximum = reference_axis.get_ylim()
    zero_fraction = -reference_minimum / (reference_maximum - reference_minimum)

    target_minimum = min(float(np.min(target_values)), 0.0)
    target_maximum = max(float(np.max(target_values)), 0.0)

    aligned_maximum = max(
        target_maximum,
        -target_minimum * (1.0 - zero_fraction) / zero_fraction,
    )
    aligned_minimum = -aligned_maximum * zero_fraction / (1.0 - zero_fraction)

    target_axis.set_ylim(aligned_minimum, aligned_maximum)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preview the CINDER full-throttle engine torque curve.",
    )
    parser.add_argument(
        "--maximum-rpm",
        type=float,
        default=5_000.0,
        help="Upper RPM shown in the preview.",
    )
    arguments = parser.parse_args()

    torque_curve = build_torque_curve()

    rpm_values = np.linspace(0.0, arguments.maximum_rpm, 1_000)
    angular_speed_values = rpm_values * _RPM_TO_RAD_PER_SECOND
    torque_values = np.array(
        [torque_curve.evaluate(float(speed)) for speed in angular_speed_values]
    )
    power_values = angular_speed_values * torque_values

    measured_rpm = np.array([point[0] for point in _BRIGGS_WOT_POINTS_RPM_FT_LBF])
    measured_torque = np.array(
        [
            foot_pound_force_to_newton_meter(point[1])
            for point in _BRIGGS_WOT_POINTS_RPM_FT_LBF
        ]
    )

    figure, torque_axis = plt.subplots()
    torque_axis.plot(rpm_values, torque_values, label="Torque")
    torque_axis.scatter(measured_rpm, measured_torque, label="Measured points")
    torque_axis.axhline(0.0, linewidth=1.0)
    torque_axis.set_xlabel("Engine speed [rpm]")
    torque_axis.set_ylabel("Crankshaft torque [N m]")
    torque_axis.grid(True, alpha=0.3)

    power_axis = torque_axis.twinx()
    power_axis.plot(rpm_values, power_values, label="Power")
    power_axis.set_ylabel("Crankshaft power [W]")

    align_zero_levels(
        reference_axis=torque_axis,
        target_axis=power_axis,
        target_values=power_values,
    )

    handles, labels = torque_axis.get_legend_handles_labels()
    power_handles, power_labels = power_axis.get_legend_handles_labels()
    torque_axis.legend(handles + power_handles, labels + power_labels)

    figure.suptitle("Full-throttle engine torque curve")
    figure.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
