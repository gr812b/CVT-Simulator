import numpy as np
from utils.theoretical_models import TheoreticalModels as tm


class SecondaryPulley:
    def __init__(
        self,
        spring_coeff_tors: float,  # Nm/rad
        spring_coeff_comp: float,  # N/m
        initial_rotation: float,  # rad
        initial_compression: float,  # m
        helix_radius: float,  # m
        # TODO: Add params for helix geometry
    ):
        self.spring_coeff_tors = spring_coeff_tors
        self.spring_coeff_comp = spring_coeff_comp
        self.initial_rotation = initial_rotation
        self.initial_compression = initial_compression
        self.helix_radius = helix_radius

    def calculate_helix_force(self, torque: float, shift_distance: float) -> float:
        return tm.gearing(torque, CVT - RATIO) / (
            2 * self.helix_radius * np.tan(HELIX - ANGLE / 2)
        )

    def calculate_spring_comp_force(self, compression: float) -> float:
        return tm.hookes_law_comp(
            self.spring_coeff_comp, self.initial_compression + compression
        )

    def calculate_spring_tors_force(self, rotation: float) -> float:
        return tm.hookes_law_tors(
            self.spring_coeff_tors, self.initial_rotation + rotation, self.helix_radius
        )
