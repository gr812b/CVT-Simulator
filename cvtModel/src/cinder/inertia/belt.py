"""Belt mass derived from the existing trapezoidal belt geometry."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Protocol


class BeltSection(Protocol):
    """
    Minimum existing geometry data needed to determine the belt mass.

    This matches ``BeltSectionSpec`` directly, so no geometry-side change
    or derived ``cross_sectional_area`` property is required.
    """

    height: float
    outer_width: float
    inner_width: float


# Compatibility alias for code that used the earlier descriptive name.
TrapezoidalBeltSection = BeltSection


@dataclass(frozen=True, slots=True)
class BeltMass:
    """Belt density, from which transport and shift mass are resolved."""

    density: float

    def __post_init__(self) -> None:
        _require_positive("density", self.density)

    def resolve(
        self,
        *,
        belt_section: BeltSection,
        outer_length: float,
    ) -> ResolvedBeltMass:
        """
        Resolve belt mass from its trapezoidal cross-section.

            A_b = h (w_outer + w_inner) / 2
            m_b = rho_b A_b L_b
        """

        _require_positive("belt_section.height", belt_section.height)
        _require_positive(
            "belt_section.outer_width",
            belt_section.outer_width,
        )
        _require_positive(
            "belt_section.inner_width",
            belt_section.inner_width,
        )
        _require_positive("outer_length", outer_length)

        cross_sectional_area = (
            0.5
            * belt_section.height
            * (belt_section.outer_width + belt_section.inner_width)
        )

        return ResolvedBeltMass(
            density=self.density,
            cross_sectional_area=cross_sectional_area,
            outer_length=outer_length,
        )


@dataclass(frozen=True, slots=True)
class ResolvedBeltMass:
    """Fixed belt geometry and resulting total belt mass."""

    density: float
    cross_sectional_area: float
    outer_length: float

    @property
    def mass(self) -> float:
        """Return m_b = rho_b A_b L_b."""

        return (
            self.density
            * self.cross_sectional_area
            * self.outer_length
        )


def _require_positive(name: str, value: float) -> None:
    if not isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive.")
