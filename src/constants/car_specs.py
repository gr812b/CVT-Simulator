# This file should contain all the constants that define the car's specs
import numpy as np
from constants.constants import INCH_TO_METER
from utils.conversions import deg_to_rad, inch_to_meter
import math

# TODO: Look into inertia as it should be of all spinning parts
ENGINE_INERTIA = 0.5  # kg*m^2
GEARBOX_RATIO = 7.556  # unitless
FRONTAL_AREA = 1.11484  # m^2
DRAG_COEFFICIENT = 0.6  # unitless
CAR_WEIGHT = 500  # lbs
CAR_MASS = CAR_WEIGHT * 0.45359237  # kg
WHEEL_RADIUS = 22 / 2 * 0.0254  # m

# TODO: These are all guesses, need to be gotten
SHEAVE_ANGLE = deg_to_rad(11.5 * 2)  # radians

BELT_CROSS_SECTIONAL_AREA = 0.0002838704  # m^2
INITIAL_FLYWEIGHT_RADIUS = 0.05  # m
HELIX_RADIUS = 0.04445  # m

BELT_ANGLE = deg_to_rad(14)
BELT_HEIGHT = inch_to_meter(0.613)  # m
BELT_LENGTH = inch_to_meter(37.53)  # m
BELT_WIDTH_TOP = inch_to_meter(0.85)  # m
BELT_WIDTH_BOTTOM = BELT_WIDTH_TOP - 2 * BELT_HEIGHT * np.tan(BELT_ANGLE)

MIN_PRIM_RADIUS = inch_to_meter(0.75)
MAX_SEC_RADIUS = inch_to_meter(4.0)
INITIAL_SHEAVE_DISPLACEMENT = inch_to_meter(0.121)

# Calculated constant
MAX_SHIFT = inch_to_meter(0.995)
CENTER_TO_CENTER = (
    BELT_LENGTH
    - np.pi * (MIN_PRIM_RADIUS + MAX_SEC_RADIUS + BELT_HEIGHT)
    + math.sqrt(
        (np.pi * (MIN_PRIM_RADIUS + MAX_SEC_RADIUS + BELT_HEIGHT)) ** 2
        - 2 * np.pi * BELT_LENGTH * (MIN_PRIM_RADIUS + MAX_SEC_RADIUS + BELT_HEIGHT)
        + BELT_LENGTH**2
        - 8 * (MAX_SEC_RADIUS - MIN_PRIM_RADIUS - BELT_HEIGHT) ** 2
    )
) / 4
