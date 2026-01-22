import numpy as np
from cvt_simulator.constants.car_specs import (
    BELT_HEIGHT,
    CENTER_TO_CENTER,
)
from cvt_simulator.utils.cvt_ratio_utils import CVTGeometry

# Module-level CVTGeometry instance using default constants
_cvt_geometry = CVTGeometry()


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
        return _cvt_geometry.r_primary(d)

    @staticmethod  # See Enman's excel sheet
    def outer_sec_radius(d: float) -> float:
        return _cvt_geometry.r_secondary(d)

    @staticmethod
    def current_cvt_ratio(d: float) -> float:
        return _cvt_geometry.ratio_from_d(d).ratio

    @staticmethod
    def current_cvt_ratio_rate_of_change(d: float, v: float) -> float:
        return _cvt_geometry.cvt_ratio_rate_of_change(d, v)

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
