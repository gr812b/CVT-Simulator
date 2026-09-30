"""Reconstruct the supplied full-throttle boundary, not a fitted power curve."""
import numpy as np
from scipy.interpolate import PchipInterpolator


def engine_curve(spec):
    # Include the same low/high-speed support as the production torque PCHIP.
    # Omitting the high-speed tail would change the last positive-drive interval.
    points = spec["points"]
    x = [0, spec["low_speed_braking_peak_speed_rad_per_s"]] + [
        p["angular_speed_rad_per_s"] for p in points
    ]
    y = [0, spec["low_speed_braking_torque_Nm"]] + [p["torque_Nm"] for p in points]
    last = x[-1]
    width = spec["high_speed_braking_transition_width_rad_per_s"]
    x.extend([last + width, last + 2 * width])
    y.extend([spec["high_speed_braking_torque_Nm"]] * 2)
    torque = PchipInterpolator(x, y)
    return lambda rpm: (
        torque(np.asarray(rpm) * np.pi / 30) * np.asarray(rpm) * np.pi / 30 / 1000
    )
