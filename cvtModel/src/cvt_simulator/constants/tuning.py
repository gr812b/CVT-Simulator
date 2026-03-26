"""Global tuning constants for CVT belt/slip behavior."""

# Belt model tuning
BELT_STICK_SPEED_THRESHOLD = 0.05
BELT_STICK_SPEED_RELATIVE_TOLERANCE = 1e-3
BELT_STICK_HYSTERESIS_RATIO = 2.6
BELT_RELAXATION_GAIN = 5.0

# Slip model tuning
SLIP_SPEED_SMOOTHING = 0.6
SLIP_CORRECTION_GAIN = 0.5
SLIP_SHIFT_STOP_BLEND_DISTANCE = 1e-3

# Slip mode hysteresis around traction-feasibility limits
SLIP_TORQUE_EXIT_MARGIN = 0.3
SLIP_TORQUE_REENTER_MARGIN = 0.8

# Slip low-speed blend back toward demand
# 0.1389 m/s ~= 0.5 km/h
SLIP_LOW_SPEED_BLEND_DEADZONE = 0.1389
SLIP_LOW_SPEED_BLEND_TRANSITION = 0.08

# High-slip lock-to-bound threshold
# 1.3889 m/s ~= 5.0 km/h
SLIP_HIGH_SPEED_LOCK_THRESHOLD = 1.3889
