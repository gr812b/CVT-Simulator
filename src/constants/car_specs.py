# This file should contain all the constants that define the car's specs


# Inertia here gets complicated, since you have inertia of drivetrain but with slipping of belt?
# Inertia of the drivetrain (kg*m^2)
ENGINE_INERTIA = 0.5

# Gear ratio of the rear gearbox (unitless)
GEARBOX_RATIO = 7.556


# Frontal area of the baja, in m^2
FRONTAL_AREA = 1.11484
# Estimate of drag coefficient
DRAG_COEFFICIENT = 0.6


# Weight in lbs
CAR_WEIGHT = 500
# Mass in kg
CAR_MASS = CAR_WEIGHT * 0.45359237
# Radius in meters
WHEEL_RADIUS = 22 / 2 * 0.0254
