"""Secondary helix-cam geometry parameterized by positive opening travel."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, isfinite

from .circular_segment import CircularSegment
from .linear_segment import LinearSegment
from .types import ScalarProfile


@dataclass(frozen=True, slots=True)
class HelixSample:
    """Secondary helix kinematics at one positive opening travel coordinate."""

    circumferential_displacement: float
    theta: float
    dtheta_dopening: float
    d2theta_dopening2: float
    helix_angle_magnitude: float


@dataclass(frozen=True, slots=True)
class HelixProfile:
    """
    Conventional torque-reactive secondary helix geometry.

    The profile coordinate ``q`` is positive secondary opening travel:

        q = -x_s,

    where the public pulley-local secondary coordinate ``x_s`` remains
    positive in the closing direction. Thus:

        q = 0       closed low-ratio reference,
        q > 0       secondary opening during an upshift.

    ``theta(q)`` is the positive spring-winding relative rotation between
    the movable and fixed secondary sheaves. A conventional torque-reactive
    secondary therefore requires:

        dtheta / dq > 0.

    This keeps the physical convention explicit: opening winds the torsional
    spring further, and positive forward transmitted torque increases the
    positive local closing force. The profile deliberately does not expose a
    handedness or coordinate-sign option; an inverse torque-reactive helix is
    outside the modeled mechanism.

    ``theta_offset`` is purely geometric clocking/reference. Torsional-spring
    preload belongs separately in ``SecondaryHelixForceSpec.initial_twist``.
    """

    circumferential_profile: ScalarProfile
    radius: float
    theta_offset: float = 0.0

    def __post_init__(self) -> None:
        if not isfinite(self.radius) or self.radius <= 0.0:
            raise ValueError("radius must be finite and positive.")

        if not isfinite(self.theta_offset):
            raise ValueError("theta_offset must be finite.")

    @property
    def opening_travel_min(self) -> float:
        """Smallest valid positive-opening coordinate q."""

        return self.circumferential_profile.x_min

    @property
    def opening_travel_max(self) -> float:
        """Largest valid positive-opening coordinate q."""

        return self.circumferential_profile.x_max

    def evaluate(self, opening_travel: float) -> HelixSample:
        """
        Evaluate spring-winding rotation and derivatives with respect to q.

        ``opening_travel`` is q = -x_s, not the signed local closing
        coordinate x_s.
        """

        profile = self.circumferential_profile.evaluate(opening_travel)

        if profile.first_derivative <= 0.0:
            raise ValueError(
                "A torque-reactive secondary helix requires positive "
                "circumferential slope du/dq."
            )

        return HelixSample(
            circumferential_displacement=profile.value,
            theta=self.theta_offset + profile.value / self.radius,
            dtheta_dopening=profile.first_derivative / self.radius,
            d2theta_dopening2=profile.second_derivative / self.radius,
            helix_angle_magnitude=atan2(
                1.0,
                profile.first_derivative,
            ),
        )


def linear_helix_segment(
    *,
    length: float,
    helix_angle_degrees: float,
) -> LinearSegment:
    """
    Build one conventional secondary-helix segment.

    The helix angle beta is measured from the circumferential direction.
    Positive opening travel q therefore gives:

        du/dq = cot(beta) > 0.

    There is intentionally no handedness parameter: CINDER's secondary helix
    is defined around the ordinary torque-reactive orientation in which
    opening winds the spring further and forward torque adds clamping force.
    """

    _validate_helix_angle(helix_angle_degrees)

    return LinearSegment(
        length=length,
        angle_degrees=90.0 - helix_angle_degrees,
    )


def circular_helix_segment(
    *,
    length: float,
    start_helix_angle_degrees: float,
    end_helix_angle_degrees: float,
) -> CircularSegment:
    """
    Build one conventional positive-slope circular secondary-helix segment.

    The circle is formed in the physical (q, u) plane and matches:

        du/dq = cot(beta) > 0

    at both endpoints. It does not assert that beta(q) itself is circular.
    """

    _validate_helix_angle(start_helix_angle_degrees)
    _validate_helix_angle(end_helix_angle_degrees)

    start_slope_angle = 90.0 - start_helix_angle_degrees
    end_slope_angle = 90.0 - end_helix_angle_degrees

    if start_slope_angle == end_slope_angle:
        return linear_helix_segment(
            length=length,
            helix_angle_degrees=start_helix_angle_degrees,
        )

    # CircularSegment's positive-slope quadrants are:
    # Q2: steep -> gentle; Q4: gentle -> steep.
    quadrant = 2 if start_slope_angle >= end_slope_angle else 4

    return CircularSegment(
        length=length,
        angle_start_degrees=start_slope_angle,
        angle_end_degrees=end_slope_angle,
        quadrant=quadrant,
    )


def _validate_helix_angle(helix_angle_degrees: float) -> None:
    if not isfinite(helix_angle_degrees):
        raise ValueError("helix_angle_degrees must be finite.")

    if not 0.0 < helix_angle_degrees < 90.0:
        raise ValueError(
            "helix_angle_degrees must lie strictly between 0 and 90."
        )
