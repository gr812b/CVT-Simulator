"""Helix-cam geometry built from a physical circumferential profile."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, isfinite

from .circular_segment import CircularSegment
from .linear_segment import LinearSegment
from .types import ScalarProfile


@dataclass(frozen=True, slots=True)
class HelixSample:
    """Helix kinematics evaluated at one local axial coordinate."""

    circumferential_displacement: float
    theta: float
    dtheta_dx: float
    d2theta_dx2: float
    helix_angle_magnitude: float


@dataclass(frozen=True, slots=True)
class HelixProfile:
    """
    Convert a physical circumferential-displacement profile u(q) into
    a local relative rotation theta(x).

        q = sigma x
        theta(x) = theta_offset + u(q) / radius

    ``q`` is the non-negative travel coordinate used by ordinary profile
    segments. ``x`` is the physical coordinate supplied by the mechanism
    using the helix. ``profile_coordinate_sign = sigma`` bridges those
    conventions without forcing every ``PiecewiseRamp`` to accept negative
    segment lengths.

    For a conventional secondary, positive x_s closes the pulley while
    the helix travels forward as the secondary opens during an upshift.
    Construct that profile with ``profile_coordinate_sign=-1`` so
    q = -x_s >= 0. The default ``+1`` retains the direct x=q convention.

    ``theta_offset`` is geometric clocking/reference. Torsional-spring
    preload belongs separately in ``SecondaryHelixForceSpec.initial_twist``.
    """

    circumferential_profile: ScalarProfile
    radius: float
    theta_offset: float = 0.0
    profile_coordinate_sign: int = 1

    def __post_init__(self) -> None:
        if not isfinite(self.radius) or self.radius <= 0.0:
            raise ValueError("radius must be finite and positive.")

        if not isfinite(self.theta_offset):
            raise ValueError("theta_offset must be finite.")

        if self.profile_coordinate_sign not in (-1, 1):
            raise ValueError(
                "profile_coordinate_sign must be either -1 or 1."
            )

    @property
    def x_min(self) -> float:
        """Smallest valid physical local coordinate x."""

        return min(
            self.profile_coordinate_sign
            * self.circumferential_profile.x_min,
            self.profile_coordinate_sign
            * self.circumferential_profile.x_max,
        )

    @property
    def x_max(self) -> float:
        """Largest valid physical local coordinate x."""

        return max(
            self.profile_coordinate_sign
            * self.circumferential_profile.x_min,
            self.profile_coordinate_sign
            * self.circumferential_profile.x_max,
        )

    def evaluate(self, x: float) -> HelixSample:
        """Evaluate theta and its derivatives with respect to x."""

        profile_coordinate = self.profile_coordinate_sign * x
        profile = self.circumferential_profile.evaluate(profile_coordinate)

        return HelixSample(
            circumferential_displacement=profile.value,
            theta=self.theta_offset + profile.value / self.radius,
            dtheta_dx=(
                self.profile_coordinate_sign
                * profile.first_derivative
                / self.radius
            ),
            d2theta_dx2=profile.second_derivative / self.radius,
            helix_angle_magnitude=atan2(
                1.0,
                abs(profile.first_derivative),
            ),
        )


def linear_helix_segment(
    *,
    length: float,
    helix_angle_degrees: float,
    handedness: int = 1,
) -> LinearSegment:
    """
    Build a direct u(q) linear segment from a constant helix angle.

    The helix angle beta is measured from the circumferential direction:

        du/dq = handedness * cot(beta)

    A ``LinearSegment`` stores the equivalent signed tangent angle from
    +q:

        slope_angle = handedness * (90 degrees - beta).
    """

    _validate_helix_angle_and_handedness(
        helix_angle_degrees=helix_angle_degrees,
        handedness=handedness,
    )

    return LinearSegment(
        length=length,
        angle_degrees=handedness * (90.0 - helix_angle_degrees),
    )


def circular_helix_segment(
    *,
    length: float,
    start_helix_angle_degrees: float,
    end_helix_angle_degrees: float,
    handedness: int = 1,
) -> CircularSegment:
    """
    Build a circular u(q) segment from endpoint helix-angle magnitudes.

    The resulting circle is in the physical (q, u) displacement plane. It
    matches du/dq = handedness * cot(beta) at both endpoints. It does not
    claim that beta(q) itself varies circularly.
    """

    _validate_helix_angle_and_handedness(
        helix_angle_degrees=start_helix_angle_degrees,
        handedness=handedness,
    )
    _validate_helix_angle_and_handedness(
        helix_angle_degrees=end_helix_angle_degrees,
        handedness=handedness,
    )

    start_slope_angle = 90.0 - start_helix_angle_degrees
    end_slope_angle = 90.0 - end_helix_angle_degrees

    if start_slope_angle == end_slope_angle:
        return linear_helix_segment(
            length=length,
            helix_angle_degrees=start_helix_angle_degrees,
            handedness=handedness,
        )

    if handedness == 1:
        quadrant = 2 if start_slope_angle >= end_slope_angle else 4
    else:
        quadrant = 3 if start_slope_angle >= end_slope_angle else 1

    return CircularSegment(
        length=length,
        angle_start_degrees=start_slope_angle,
        angle_end_degrees=end_slope_angle,
        quadrant=quadrant,
    )


def _validate_helix_angle_and_handedness(
    *,
    helix_angle_degrees: float,
    handedness: int,
) -> None:
    if not isfinite(helix_angle_degrees):
        raise ValueError("helix_angle_degrees must be finite.")

    if not 0.0 < helix_angle_degrees < 90.0:
        raise ValueError(
            "helix_angle_degrees must lie strictly between 0 and 90."
        )

    if handedness not in (-1, 1):
        raise ValueError("handedness must be either -1 or 1.")
