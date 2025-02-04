# This file should contain all the constants that define the car's specs
import numpy as np

# TODO: Look into inertia as it should be of all spinning parts
ENGINE_INERTIA = 0.5  # kg*m^2
GEARBOX_RATIO = 7.556  # unitless
FRONTAL_AREA = 1.11484  # m^2
DRAG_COEFFICIENT = 0.6  # unitless
CAR_WEIGHT = 500  # lbs
CAR_MASS = CAR_WEIGHT * 0.45359237  # kg
WHEEL_RADIUS = 22 / 2 * 0.0254  # m

# TODO: These are all guesses, need to be gotten
SHEAVE_ANGLE = np.pi/9.5  # radians
BELT_WIDTH = 0.05  # m
BELT_CROSS_SECTIONAL_AREA = 0.02  # m^2
INNER_PRIMARY_PULLEY_RADIUS = 0.1  # m
INNER_SECONDARY_PULLEY_RADIUS = 0.25  # m
INITIAL_FLYWEIGHT_RADIUS = 0.1  # m
HELIX_RADIUS = 0.05  # m
CENTER_TO_CENTER = 0.5  # m