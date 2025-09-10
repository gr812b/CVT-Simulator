import numpy as np
from models.dataTypes import HelixForceBreakdown, SecondaryForceBreakdown, SpringTorsForceBreakdown, springCompForceBreakdown
from utils.theoretical_models import TheoreticalModels as tm
from constants.car_specs import (
    BELT_HEIGHT,
    MAX_SHIFT,
    HELIX_RADIUS,
)
from models.ramps import LinearSegment, PiecewiseRamp


class SecondaryPulleyModel:
    def __init__(
        self,
        spring_coeff_tors: float,  # Nm/rad
        spring_coeff_comp: float,  # N/m
        initial_rotation: float,  # rad
        initial_compression: float,  # m
        ramp_type: int,
    ):
        self.spring_coeff_tors = spring_coeff_tors
        self.spring_coeff_comp = spring_coeff_comp
        self.initial_rotation = initial_rotation
        self.initial_compression = initial_compression
        self.helix_radius = HELIX_RADIUS
        self.ramp_type = ramp_type

        if self.ramp_type == 1:
            self.ramp = PiecewiseRamp()
            self.ramp.add_segment(LinearSegment(x_start=0, x_end=MAX_SHIFT, slope=-0.3))
        elif self.ramp_type == 2:
            self.ramp = PiecewiseRamp()
            self.ramp.add_segment(
                LinearSegment(x_start=0, x_end=MAX_SHIFT / 2, slope=-0.4)
            )
            self.ramp.add_segment(
                LinearSegment(x_start=MAX_SHIFT / 2, x_end=MAX_SHIFT, slope=-0.25)
            )

    def get_breakdown(self, torque: float, shift_distance: float) -> SecondaryForceBreakdown:
        spring_comp_force_breakdown = self._calculate_spring_comp_force(shift_distance)
        helix_force_breakdown = self._calculate_helix_force(
            torque, shift_distance
        )
        net = helix_force_breakdown.net + spring_comp_force_breakdown.net
        return SecondaryForceBreakdown(
            spring_comp_force_breakdown,
            helix_force_breakdown,
            net,
        )

    def _calculate_helix_force(
        self, torque: float, shift_distance: float
    ) -> HelixForceBreakdown:
        spring_torque_breakdown = self._calculate_spring_tors_torque(shift_distance)
        secondary_radius = tm.outer_sec_radius(shift_distance) - BELT_HEIGHT / 2

        if shift_distance < 0:  # TODO: remove
            shift_distance = 0
        if shift_distance > MAX_SHIFT:
            shift_distance = MAX_SHIFT

        angle = np.arctan(self.ramp.slope(shift_distance))

        net = (torque + spring_torque_breakdown.net) / (2 * np.tan(angle) * secondary_radius)

        return HelixForceBreakdown(
            torque,
            spring_torque_breakdown,
            angle,
            secondary_radius,
            (2 * np.tan(angle) * secondary_radius),
            net,
        )

    def _calculate_spring_comp_force(self, compression: float) -> springCompForceBreakdown:
        net = tm.hookes_law_comp(
            self.spring_coeff_comp, self.initial_compression + compression
        )
        return springCompForceBreakdown(
            compression,
            net,
        )

    # TODO: Determine relationship between shift distance and rotation
    def _calculate_rotation(self, shift_distance: float) -> float:
        return shift_distance * self.ramp.slope(shift_distance) * 2 / HELIX_RADIUS

    def _calculate_spring_tors_torque(self, shift_distance: float) -> SpringTorsForceBreakdown:

        if shift_distance < 0:  # TODO: remove
            shift_distance = 0
        if shift_distance > MAX_SHIFT:
            shift_distance = MAX_SHIFT

        rotation = self.initial_rotation + self._calculate_rotation(shift_distance)
        net = tm.hookes_law_tors(self.spring_coeff_tors, rotation)
        return SpringTorsForceBreakdown(
            rotation,
            net,
        )

