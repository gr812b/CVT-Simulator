"""Resolved belt-pulley geometry at one global shift coordinate."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RadiusAtShift:
    """One belt reference radius and its global-shift derivatives."""

    effective: float
    outer: float
    center_of_mass: float

    d_effective_ds: float
    d2_effective_ds2: float


@dataclass(frozen=True, slots=True)
class AxialCoordinateAtShift:
    """One physical axial coordinate x(s) and its global derivatives."""

    value: float
    d_value_ds: float
    d2_value_ds2: float


@dataclass(frozen=True, slots=True)
class GeometryPosition:
    """All geometry needed by one RHS evaluation at a shift position."""

    shift: float

    primary: RadiusAtShift
    secondary: RadiusAtShift

    primary_wrap_angle: float
    secondary_wrap_angle: float

    primary_axial_coordinate: AxialCoordinateAtShift
    secondary_axial_coordinate: AxialCoordinateAtShift
    belt_axial_coordinate: AxialCoordinateAtShift
