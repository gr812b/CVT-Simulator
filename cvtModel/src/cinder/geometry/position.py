# cinder/geometry/position.py

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RadiusAtShift:
    effective: float
    outer: float
    center_of_mass: float

    d_effective_ds: float
    d2_effective_ds2: float

@dataclass(frozen=True, slots=True)
class AxialCoordinateAtShift:
    value: float
    d_value_ds: float
    d2_value_ds2: float


@dataclass(frozen=True, slots=True)
class GeometryPosition:
    shift: float

    primary: RadiusAtShift
    secondary: RadiusAtShift

    primary_wrap_angle: float
    secondary_wrap_angle: float

    primary_axial_coordinate: AxialCoordinateAtShift
    secondary_axial_coordinate: AxialCoordinateAtShift