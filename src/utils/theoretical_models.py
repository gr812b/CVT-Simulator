import numpy as np


class TheoreticalModels:
    """
    A collection of theoretical models and equations.
    """

    @staticmethod
    def hookes_law_comp(k: float, x: float) -> float:
        return k * x

    @staticmethod
    def hookes_law_tors(k: float, θ: float, r: float) -> float:
        return k * θ / r

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

    @staticmethod  # See theoretical model TM:D2R
    def shift_to_pulley_radius_prim(d: float, sheave_angle: float) -> float:
        return d / (2 * np.tan(sheave_angle / 2))

    @staticmethod  # See theoretical model TM:D2R
    def shift_to_pulley_radius_sec(
        d: float, sheave_angle: float, belt_width: float
    ) -> float:
        return (belt_width - d / 2) / np.tan(sheave_angle / 2)

    @staticmethod
    def current_primary_radius(
        d: float, sheave_angle: float, initial_radius: float
    ) -> float:
        return initial_radius + TheoreticalModels.shift_to_pulley_radius_prim(
            d, sheave_angle
        )

    @staticmethod
    def current_secondary_radius(
        d: float, sheave_angle: float, belt_width: float, initial_radius: float
    ) -> float:
        return initial_radius - TheoreticalModels.shift_to_pulley_radius_sec(
            d, sheave_angle, belt_width
        )

    @staticmethod
    def current_cvt_ratio(
        d: float,
        sheave_angle: float,
        belt_width: float,
        initial_primary_radius: float,
        initial_secondary_radius: float,
    ) -> float:
        secondary_radius = TheoreticalModels.current_secondary_radius(
            d, sheave_angle, belt_width, initial_primary_radius
        )
        primary_radius = TheoreticalModels.current_primary_radius(
            d, sheave_angle, initial_secondary_radius
        )
        # TODO: Remove debug prints
        # print(f"Primary: {primary_radius}, Secondary: {secondary_radius}, ratio: {primary_radius / secondary_radius}")
        return primary_radius / secondary_radius
