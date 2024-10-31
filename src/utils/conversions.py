import math


def rpm_to_rad_s(rpm):
    return rpm * (2 * math.pi) / 60


def rad_s_to_rpm(rad_s):
    return rad_s * 60 / (2 * math.pi)


def rad_to_deg(rad):
    return rad * 180 / math.pi


def deg_to_rad(deg):
    return deg * math.pi / 180


def circumference(radius):
    return 2 * math.pi * radius
