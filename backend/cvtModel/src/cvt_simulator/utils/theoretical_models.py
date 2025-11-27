import numpy as np
import math
from cvt_simulator.constants.car_specs import (
    BELT_HEIGHT,
    MIN_PRIM_RADIUS,
    INITIAL_SHEAVE_DISPLACEMENT,
    BELT_ANGLE,
    CENTER_TO_CENTER,
    BELT_LENGTH,
)


class TheoreticalModels:
    """
    A collection of theoretical models and equations.
    """

    @staticmethod
    def hookes_law_comp(k: float, x: float) -> float:
        return k * x

    @staticmethod
    def hookes_law_tors(k: float, θ: float) -> float:
        return k * θ

    @staticmethod
    def centrifugal_force(m: float, ω: float, r: float) -> float:
        return m * ω**2 * r

    @staticmethod
    def air_resistance(ρ: float, v: float, A: float, C_d: float) -> float:
        return 0.5 * ρ * v**2 * A * C_d

    @staticmethod
    def torque(P: float, ω: float) -> float:
        return P / ω

    @staticmethod
    def gearing(t: float, r: float) -> float:
        return t * r

    @staticmethod
    def static_friction(μ: float, N: float) -> float:
        return μ * N

    @staticmethod
    def capstan_equation(T: float, θ: float, μ: float) -> float:
        return T * np.exp(μ * θ)

    @staticmethod  # TODO: See if this is actually used outside of derivations / in this format
    def newtons_second_law(m: float, a: float) -> float:
        return m * a

    @staticmethod  # See Enman's excel sheet
    def outer_prim_radius(d: float) -> float:
        engage_distance = MIN_PRIM_RADIUS + BELT_HEIGHT
        current_distance = (
            (d - INITIAL_SHEAVE_DISPLACEMENT) / (2 * np.tan(BELT_ANGLE))
            + MIN_PRIM_RADIUS
            + BELT_HEIGHT
        )
        # print(f"Engage: {engage_distance}, Current: {current_distance}")
        return max(engage_distance, current_distance)

    @staticmethod  # See Enman's excel sheet
    def outer_sec_radius(d: float) -> float:
        prim_radius = TheoreticalModels.outer_prim_radius(d)
        return (
            2 * prim_radius
            - np.pi * CENTER_TO_CENTER
            + math.sqrt(
                (np.pi * CENTER_TO_CENTER) ** 2
                - 8 * np.pi * CENTER_TO_CENTER * prim_radius
                + 4 * BELT_LENGTH * CENTER_TO_CENTER
                - 8 * CENTER_TO_CENTER**2
            )
        ) / 2

    @staticmethod
    def current_cvt_ratio(d: float) -> float:
        primary_radius = TheoreticalModels.outer_prim_radius(d) - BELT_HEIGHT / 2
        secondary_radius = TheoreticalModels.outer_sec_radius(d) - BELT_HEIGHT / 2
        # TODO: Remove debug prints
        # print(f"Primary: {primary_radius}, Secondary: {secondary_radius}, ratio: {secondary_radius / primary_radius}")
        return secondary_radius / primary_radius

    # ---------------------------------------------------------
    # Derivative of ratio wrt d (di/dd)
    # ---------------------------------------------------------
    @staticmethod
    def cvt_ratio_derivative_wrt_d(d: float) -> float:
        # primary + derivative
        engage_distance = MIN_PRIM_RADIUS + BELT_HEIGHT
        current_distance = (
            (d - INITIAL_SHEAVE_DISPLACEMENT) / (2 * np.tan(BELT_ANGLE))
            + MIN_PRIM_RADIUS
            + BELT_HEIGHT
        )
        prim_radius = max(engage_distance, current_distance)
        # dR_p/dd = 0 if clamped, else 1/(2tan(theta))
        if current_distance <= engage_distance:
            dRp_dd = 0.0
        else:
            dRp_dd = 1.0 / (2.0 * np.tan(BELT_ANGLE))

        # secondary + derivative
        C = CENTER_TO_CENTER
        L = BELT_LENGTH
        Delta = math.sqrt(
            max(
                (np.pi * C) ** 2 - 8 * np.pi * C * prim_radius + 4 * L * C - 8 * C**2,
                1e-12,
            )
        )
        dRs_dRp = 1.0 - (2.0 * np.pi * C) / Delta
        dRs_dd = dRs_dRp * dRp_dd
        sec_radius = (2 * prim_radius - np.pi * C + Delta) / 2.0

        # effective radii (belt centerline)
        P = prim_radius - BELT_HEIGHT / 2.0
        S = sec_radius - BELT_HEIGHT / 2.0
        Pp = dRp_dd
        Sp = dRs_dd

        # quotient rule: (S'P - SP') / P^2
        if abs(P) < 1e-12:
            return 0.0
        return (Sp * P - S * Pp) / (P * P)

    # ---------------------------------------------------------
    # di/dt = (di/dd) * v
    # ---------------------------------------------------------
    @staticmethod
    def current_cvt_ratio_rate_of_change(d: float, v: float) -> float:
        di_dd = TheoreticalModels.cvt_ratio_derivative_wrt_d(d)
        return di_dd * v

    @staticmethod
    def wrap_angle(
        primary_radius: float,
        secondary_radius: float,
    ):
        return 2 * np.arcsin(
            (secondary_radius - primary_radius) / (2 * CENTER_TO_CENTER)
        )

    @staticmethod
    def primary_wrap_angle(d: float):
        primary_radius = TheoreticalModels.outer_prim_radius(d) - BELT_HEIGHT / 2
        secondary_radius = TheoreticalModels.outer_sec_radius(d) - BELT_HEIGHT / 2
        wrap_offset = TheoreticalModels.wrap_angle(primary_radius, secondary_radius)
        # print(f"Ratio: {secondary_radius/primary_radius}, wrap: {wrap_offset}")
        if primary_radius <= secondary_radius:
            return np.pi - wrap_offset
        else:
            return np.pi + wrap_offset

    @staticmethod
    def secondary_wrap_angle(d: float):
        primary_radius = TheoreticalModels.outer_prim_radius(d) - BELT_HEIGHT / 2
        secondary_radius = TheoreticalModels.outer_sec_radius(d) - BELT_HEIGHT / 2
        wrap_offset = TheoreticalModels.wrap_angle(primary_radius, secondary_radius)
        if primary_radius <= secondary_radius:
            return np.pi + wrap_offset
        else:
            return np.pi - wrap_offset
