# This file should contain all the constants that define the car's specs


# TODO: Look into inertia as it should be of all spinning parts
ENGINE_INERTIA = 0.5  # kg*m^2
GEARBOX_RATIO = 7.556  # unitless
FRONTAL_AREA = 1.11484  # m^2
DRAG_COEFFICIENT = 0.6  # unitless
CAR_WEIGHT = 500  # lbs
CAR_MASS = CAR_WEIGHT * 0.45359237  # kg
WHEEL_RADIUS = 22 / 2 * 0.0254  # m

# TODO: These are all guesses, need to be gotten
SHEAVE_ANGLE = 30  # degrees TODO: Check if this is in degrees or radians
BELT_WIDTH = 0.5  # m
INITIAL_PRIMARY_PULLEY_RADIUS = 0.1  # m
INITIAL_SECONDARY_PULLEY_RADIUS = 0.15  # m
INITIAL_FLYWEIGHT_RADIUS = 0.05  # m
HELIX_RADIUS = 0.1  # m
