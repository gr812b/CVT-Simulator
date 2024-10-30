import math


def rpm_to_rad_s(rpm):
    return rpm * (2 * math.pi) / 60


def rad_s_to_rpm(rad_s):
    return rad_s * 60 / (2 * math.pi)
