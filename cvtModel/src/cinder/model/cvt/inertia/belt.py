"""Belt transport mass resolved on the belt center-of-mass path."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi
from typing import Protocol


class TrapezoidalBeltSection(Protocol):
    """Minimum belt-section data needed to determine transport mass."""

    height: float
    outer_width: float
    inner_width: float
    center_of_mass_depth_from_outer: float


# Compatibility name for existing consumers. It refers to the same protocol.
BeltSection = TrapezoidalBeltSection


@dataclass(frozen=True, slots=True)
class BeltMass:
    """Belt density, from which transport and shift mass are resolved."""

    density: float

    def __post_init__(self) -> None:
        _require_positive("density", self.density)

    def resolve(
        self,
        *,
        belt_section: TrapezoidalBeltSection,
        outer_length: float,
    ) -> "ResolvedBeltMass":
        """Resolve mass from the trapezoid and its centroid-path length.

        The supplied CVT belt length is the outer-surface path length. Belt
        transport inertia follows the belt mass centroid, which is a fixed
        distance ``y_cm`` inward from that path. Because the two wrap angles
        always sum to 2*pi,

            L_cm = L_outer - 2*pi*y_cm,
            A_b  = h (w_outer + w_inner) / 2,
            m_b  = rho_b A_b L_cm.

        This is the same fixed-length reduction used by the distributed wrap
        derivation; it does not introduce a new belt degree of freedom.
        """

        _require_positive("belt_section.height", belt_section.height)
        _require_positive("belt_section.outer_width", belt_section.outer_width)
        _require_positive("belt_section.inner_width", belt_section.inner_width)
        _require_positive("outer_length", outer_length)
        _require_nonnegative(
            "belt_section.center_of_mass_depth_from_outer",
            belt_section.center_of_mass_depth_from_outer,
        )

        cross_sectional_area = (
            0.5
            * belt_section.height
            * (belt_section.outer_width + belt_section.inner_width)
        )
        center_of_mass_path_length = (
            outer_length - 2.0 * pi * belt_section.center_of_mass_depth_from_outer
        )
        _require_positive("center_of_mass_path_length", center_of_mass_path_length)

        return ResolvedBeltMass(
            density=self.density,
            cross_sectional_area=cross_sectional_area,
            outer_length=outer_length,
            center_of_mass_path_length=center_of_mass_path_length,
        )


@dataclass(frozen=True, slots=True)
class ResolvedBeltMass:
    """Fixed belt geometry and resulting transport mass."""

    density: float
    cross_sectional_area: float
    outer_length: float
    center_of_mass_path_length: float

    @property
    def mass(self) -> float:
        """Return ``m_b = rho_b A_b L_b,cm``."""

        return self.density * self.cross_sectional_area * self.center_of_mass_path_length

    @property
    def linear_density(self) -> float:
        """Return the material line density ``rho_b A_b``."""

        return self.density * self.cross_sectional_area


def _require_positive(name: str, value: float) -> None:
    if not isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive.")


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
