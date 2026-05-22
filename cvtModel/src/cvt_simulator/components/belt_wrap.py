"""Belt centrifugal force model.

Calculates the radial centrifugal force component from the rotating CVT belt.
"""
import numpy as np
from cvt_simulator.geometry.cvt_geometry import CVT_GEOMETRY
from cvt_simulator.sim_utils.system_state import SystemState
from cvt_simulator.core.data_types import BeltWrapBreakdown
from cvt_simulator.constants.car_specs import (
    SHEAVE_ANGLE,
    BELT_CROSS_SECTIONAL_AREA,
)
from cvt_simulator.constants.constants import RUBBER_DENSITY


class BeltWrap:
    """CVT belt centrifugal force calculator."""

    def __init__(self, is_primary: bool):
        """Initialize belt with geometric constants.

        Args:
            is_primary: If True, use primary pulley geometry; otherwise secondary.
        """
        # Default to primary geometry
        self.is_primary = is_primary

    def axial_centrifugal_force(self, state: SystemState) -> BeltWrapBreakdown:
        """
        Calculate belt centrifugal force.

        Args:
            state: Current system state

        Returns:
            Centrifugal force [N]
        """
        s = state.s
        v_b = state.v_b

        # use primary/secondary wrap depending on configuration
        if self.is_primary:
            wrap_angle = CVT_GEOMETRY.primary_wrap_angle(s)
        else:
            wrap_angle = CVT_GEOMETRY.secondary_wrap_angle(s)

        beta = SHEAVE_ANGLE / 2

        belt_force = (
            RUBBER_DENSITY * BELT_CROSS_SECTIONAL_AREA * v_b**2 * wrap_angle
        ) / (2 * np.tan(beta))

        return BeltWrapBreakdown(wrap_angle=wrap_angle, belt_force=belt_force)

