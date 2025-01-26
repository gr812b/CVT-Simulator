import numpy as np
from utils.theoretical_models import TheoreticalModels as tm
from constants.car_specs import (
    SHEAVE_ANGLE,
    BELT_WIDTH,
    INITIAL_PRIMARY_PULLEY_RADIUS,
    INITIAL_SECONDARY_PULLEY_RADIUS,
)


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
        cvt_ratio = tm.current_cvt_ratio(
            shift_distance,
            SHEAVE_ANGLE,
            BELT_WIDTH,
            INITIAL_PRIMARY_PULLEY_RADIUS,
            INITIAL_SECONDARY_PULLEY_RADIUS,
        )
        helix_angle = np.pi / 6  # TODO: Calculate helix angle
        
        return tm.gearing(torque, cvt_ratio) / (
            2 * self.helix_radius * np.tan(helix_angle / 2)
        )

    def calculate_spring_comp_force(self, compression: float) -> float:
        return tm.hookes_law_comp(
            self.spring_coeff_comp, self.initial_compression + compression
        )

    def calculate_spring_tors_force(self, rotation: float) -> float:
        # TODO: Check if force applies at helix radius
        return tm.hookes_law_tors(
            self.spring_coeff_tors, self.initial_rotation + rotation, self.helix_radius 
        )

    # TODO: Determine relationship between shift distance and rotation
    def calculate_net_force(
        self, torque: float, shift_distance: float, rotation: float
    ) -> float:
        helix_force = self.calculate_helix_force(torque, shift_distance)
        spring_comp_force = self.calculate_spring_comp_force(shift_distance)
        spring_tors_force = self.calculate_spring_tors_force(rotation)
        return helix_force + spring_comp_force + spring_tors_force
