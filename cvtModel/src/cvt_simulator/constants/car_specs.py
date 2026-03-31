# This file contains all the constants that define the car's specs
import numpy as np
from cvt_simulator.utils.conversions import deg_to_rad, inch_to_meter
import math
from pydantic import BaseModel, Field, computed_field


class CarSpecs(BaseModel):
    """
    Configuration class for CVT simulator car specifications.

    Base constants can be overridden to simulate different car configurations.
    Calculated constants are computed automatically from base values.
    """

    # Inertia values
    engine_inertia: float = Field(default=0.1, description="Engine inertia in kg*m^2")
    secondary_inertia: float = Field(
        default=0.1, description="Secondary CVT pulley inertia in kg*m^2"
    )
    gearbox_inertia: float = Field(
        default=0.05, description="Gearbox inertia in kg*m^2"
    )
    wheel_inertia: float = Field(
        default=0.2, description="Wheel inertia in kg*m^2 (all wheels)"
    )
    driveline_inertia: float = Field(
        default=0.5,
        description="Driveline inertia in kg*m^2 (includes sec CVT, gearbox, axles, wheels, hubs, etc)",
    )

    # Drivetrain
    gearbox_ratio: float = Field(default=7.556, description="Gearbox ratio (unitless)")
    wheel_radius: float = Field(
        default=22 / 2 * 0.0254, description="Wheel radius in meters"
    )

    # Aerodynamics
    frontal_area: float = Field(default=1.11484, description="Frontal area in m^2")
    drag_coefficient: float = Field(
        default=0.6, description="Drag coefficient (unitless)"
    )
    rolling_resistance_coefficient: float = Field(
        default=0.015, description="Rolling resistance coefficient (unitless)"
    )

    # Pulley geometry
    # TODO: These are all guesses, need to be gotten
    sheave_angle: float = Field(
        default=deg_to_rad(11.5 * 2), description="Sheave angle in radians"
    )
    initial_flyweight_radius: float = Field(
        default=0.04878, description="Initial flyweight radius in meters"
    )
    helix_radius: float = Field(default=0.04445, description="Helix radius in meters")

    # Belt specifications
    belt_height: float = Field(
        default=inch_to_meter(0.613), description="Belt height in meters"
    )
    belt_length: float = Field(
        default=inch_to_meter(37.53), description="Belt length in meters"
    )
    belt_width_top: float = Field(
        default=inch_to_meter(0.840), description="Belt width at top in meters"
    )
    belt_width_bottom: float = Field(
        default=inch_to_meter(0.662), description="Belt width at bottom in meters"
    )

    # Pulley radii
    min_prim_radius: float = Field(
        default=inch_to_meter(1.625 / 2),
        description="Minimum primary pulley radius in meters",
    )
    max_sec_radius: float = Field(
        default=inch_to_meter(4.0),
        description="Maximum secondary pulley radius in meters",
    )
    initial_sheave_displacement: float = Field(
        default=inch_to_meter(0.088 + 0.010),
        description="Initial sheave displacement in meters",
    )

    # Computed fields (calculated from base values)
    @computed_field
    @property
    def belt_angle(self) -> float:
        """Belt width at bottom in meters, calculated from top width, height and angle."""
        return math.atan(
            (self.belt_width_top - self.belt_width_bottom) / (2 * self.belt_height)
        )

    @computed_field
    @property
    def belt_cross_sectional_area(self) -> float:
        """Belt cross-sectional area in m^2."""
        return (self.belt_width_top + self.belt_width_bottom) / 2 * self.belt_height

    @computed_field
    @property
    def max_shift(self) -> float:
        """Maximum shift distance in meters (calculated constant)."""
        return inch_to_meter(0.75)

    @computed_field
    @property
    def center_to_center(self) -> float:
        """Center-to-center distance between pulleys in meters (calculated from belt and pulley geometry)."""
        return (
            self.belt_length
            - np.pi * (self.min_prim_radius + self.max_sec_radius + self.belt_height)
            + math.sqrt(
                (
                    np.pi
                    * (self.min_prim_radius + self.max_sec_radius + self.belt_height)
                )
                ** 2
                - 2
                * np.pi
                * self.belt_length
                * (self.min_prim_radius + self.max_sec_radius + self.belt_height)
                + self.belt_length**2
                - 8
                * (self.max_sec_radius - self.min_prim_radius - self.belt_height) ** 2
            )
        ) / 4

    @computed_field
    @property
    def min_effective_cvt_ratio(self) -> float:
        """Minimum effective CVT ratio (unitless) at zero shift distance."""
        from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm

        return tm.current_effective_cvt_ratio(0)

    @computed_field
    @property
    def max_effective_cvt_ratio(self) -> float:
        """Maximum effective CVT ratio (unitless) at max shift distance."""
        from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm

        return tm.current_effective_cvt_ratio(self.max_shift)

    class Config:
        """Pydantic configuration."""

        frozen = False  # Allow modification for future use cases
        validate_assignment = True  # Re-validate on field changes


# Default car specs instance for backward compatibility
_default_specs = CarSpecs()

# Export constants as module-level variables for backward compatibility
ENGINE_INERTIA = _default_specs.engine_inertia
SECONDARY_INERTIA = _default_specs.secondary_inertia
GEARBOX_INERTIA = _default_specs.gearbox_inertia
WHEEL_INERTIA = _default_specs.wheel_inertia
DRIVELINE_INERTIA = _default_specs.driveline_inertia
GEARBOX_RATIO = _default_specs.gearbox_ratio
FRONTAL_AREA = _default_specs.frontal_area
DRAG_COEFFICIENT = _default_specs.drag_coefficient
ROLLING_RESISTANCE_COEFFICIENT = _default_specs.rolling_resistance_coefficient
WHEEL_RADIUS = _default_specs.wheel_radius
SHEAVE_ANGLE = _default_specs.sheave_angle
INITIAL_FLYWEIGHT_RADIUS = _default_specs.initial_flyweight_radius
HELIX_RADIUS = _default_specs.helix_radius
BELT_ANGLE = _default_specs.belt_angle
BELT_HEIGHT = _default_specs.belt_height
BELT_LENGTH = _default_specs.belt_length
BELT_WIDTH_TOP = _default_specs.belt_width_top
BELT_WIDTH_BOTTOM = _default_specs.belt_width_bottom
BELT_CROSS_SECTIONAL_AREA = _default_specs.belt_cross_sectional_area
MIN_PRIM_RADIUS = _default_specs.min_prim_radius
MAX_SEC_RADIUS = _default_specs.max_sec_radius
INITIAL_SHEAVE_DISPLACEMENT = _default_specs.initial_sheave_displacement
MAX_SHIFT = _default_specs.max_shift
CENTER_TO_CENTER = _default_specs.center_to_center
MIN_EFFECTIVE_CVT_RATIO = _default_specs.min_effective_cvt_ratio
MAX_EFFECTIVE_CVT_RATIO = _default_specs.max_effective_cvt_ratio
