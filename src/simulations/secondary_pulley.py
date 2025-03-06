import numpy as np
from utils.theoretical_models import TheoreticalModels as tm
from constants.car_specs import (
    SHEAVE_ANGLE,
    MAX_SHIFT,
    INNER_SECONDARY_PULLEY_RADIUS,
)
from utils.ramp_representation import LinearSegment, PiecewiseRamp


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
        self.ramp = PiecewiseRamp()
        self.ramp.add_segment(LinearSegment(x_start=0, x_end=1, slope=-0.5774))

    # TODO: Look into how the torsional sping affects this torque value
    def calculate_helix_force(
        self, torque: float, spring_torque: float, shift_distance: float
    ) -> float:
        secondary_radius = tm.current_secondary_radius(
            shift_distance, SHEAVE_ANGLE, INNER_SECONDARY_PULLEY_RADIUS
        )

        if shift_distance < 0:  # TODO: remove
            shift_distance = 0
        if shift_distance > MAX_SHIFT:
            shift_distance = MAX_SHIFT

        angle = np.arctan(self.ramp.slope(shift_distance))

        return (torque + spring_torque) / (2 * np.tan(angle) * secondary_radius)

    def calculate_spring_comp_force(self, compression: float) -> float:
        return tm.hookes_law_comp(
            self.spring_coeff_comp, self.initial_compression + compression
        )

    def calculate_spring_tors_torque(self, shift_distance: float) -> float:

        if shift_distance < 0:  # TODO: remove
            shift_distance = 0
        if shift_distance > MAX_SHIFT:
            shift_distance = MAX_SHIFT

        rotation = (
            self.initial_rotation + self.ramp.height(shift_distance) / self.helix_radius
        )
        return tm.hookes_law_tors(self.spring_coeff_tors, rotation)

    # TODO: Determine relationship between shift distance and rotation
    def calculate_net_force(self, torque: float, shift_distance: float) -> float:
        spring_comp_force = self.calculate_spring_comp_force(shift_distance)
        spring_tors_torque = self.calculate_spring_tors_torque(shift_distance)
        helix_force = self.calculate_helix_force(
            torque, spring_tors_torque, shift_distance
        )

        # print(f"Compression force: {spring_comp_force}, Torsion Force: {spring_tors_torque / self.helix_radius}, Helix Force: {helix_force}, Torque: {torque}")
        return helix_force + spring_comp_force
