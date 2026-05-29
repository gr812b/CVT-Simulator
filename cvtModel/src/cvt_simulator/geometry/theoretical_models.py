import numpy as np
from cvt_simulator.constants.car_specs import CENTER_TO_CENTER, BELT_HEIGHT, BELT_WIDTH_BOTTOM, BELT_WIDTH_TOP
# from cvt_simulator.geometry.cvt_geometry import CVT_GEOMETRY

# Use shared CVT geometry instance
# _cvt_geometry = CVT_GEOMETRY


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
    def sgn(x: float) -> float:
        """Sign function: returns -1, 0, or 1 based on sign of x."""
        if x > 0:
            return 1.0
        elif x < 0:
            return -1.0
        else:
            return 0.0

    @staticmethod
    def rolling_resistance(C_rr: float, m: float, g: float, α: float) -> float:
        """Calculate rolling resistance force. C_rr is coefficient, m is mass, α is incline angle."""
        return C_rr * m * g * np.cos(α)

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

    # @staticmethod  # See Enman's excel sheet
    # def primary_outer_radius(d: float) -> float:
    #     return _cvt_geometry.primary_outer_radius(d)

    # @staticmethod  # See Enman's excel sheet
    # def secondary_outer_radius(d: float) -> float:
    #     return _cvt_geometry.secondary_outer_radius(d)

    # @staticmethod
    # def primary_effective_radius(d: float) -> float:
    #     return _cvt_geometry.primary_effective_radius(d)

    # @staticmethod
    # def secondary_effective_radius(d: float) -> float:
    #     return _cvt_geometry.secondary_effective_radius(d)

    @staticmethod
    def centroid_offset() -> float:
        """Centroid offset from belt centerline (used by belt centroid radius)."""
        return (
            BELT_HEIGHT * (BELT_WIDTH_TOP + 2 * BELT_WIDTH_BOTTOM)
            / (3 * (BELT_WIDTH_TOP + BELT_WIDTH_BOTTOM))
        )

    @staticmethod
    def primary_centroid_radius(d: float) -> float:
        """Primary centroid radius measured to belt centroid from CVT geometry."""
        r_eff = TheoreticalModels.primary_effective_radius(d)
        return r_eff + BELT_HEIGHT / 2 - TheoreticalModels.centroid_offset()

    @staticmethod
    def secondary_centroid_radius(d: float) -> float:
        """Secondary centroid radius measured to belt centroid from CVT geometry."""
        r_eff = TheoreticalModels.secondary_effective_radius(d)
        return r_eff + BELT_HEIGHT / 2 - TheoreticalModels.centroid_offset()

    # @staticmethod
    # def primary_radius_rate_of_change(d: float) -> float:
    #     """Get dr_p/dd at current shift position."""
    #     return _cvt_geometry._primary_outer_radius_shift_derivative(d)

    # @staticmethod
    # def secondary_radius_rate_of_change(d: float) -> float:
    #     """Get dr_s/dd at current shift position."""
    #     return _cvt_geometry._secondary_outer_radius_shift_derivative(d)

    # @staticmethod
    # def current_effective_cvt_ratio(d: float) -> float:
    #     return _cvt_geometry.effective_cvt_ratio(d)

    # @staticmethod
    # def current_effective_cvt_ratio_time_derivative(d: float, v: float) -> float:
    #     return _cvt_geometry.effective_cvt_ratio_time_derivative(d, v)

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
        primary_radius = TheoreticalModels.primary_effective_radius(d)
        secondary_radius = TheoreticalModels.secondary_effective_radius(d)
        wrap_offset = TheoreticalModels.wrap_angle(primary_radius, secondary_radius)
        # print(f"Ratio: {secondary_radius/primary_radius}, wrap: {wrap_offset}")
        if primary_radius <= secondary_radius:
            return np.pi - wrap_offset
        else:
            return np.pi + wrap_offset

    @staticmethod
    def secondary_wrap_angle(d: float):
        primary_radius = TheoreticalModels.primary_effective_radius(d)
        secondary_radius = TheoreticalModels.secondary_effective_radius(d)
        wrap_offset = TheoreticalModels.wrap_angle(primary_radius, secondary_radius)
        if primary_radius <= secondary_radius:
            return np.pi + wrap_offset
        else:
            return np.pi - wrap_offset
