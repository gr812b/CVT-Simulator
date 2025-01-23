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
        return m * ω**2 / r

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
    def shift_to_pulley_radius(d: float, Φ: float) -> float:
        return d / (2 * np.tan(Φ / 2))
