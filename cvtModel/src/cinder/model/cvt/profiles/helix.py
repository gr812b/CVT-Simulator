"""Pulley-local helix-cam geometry parameterized by positive opening travel."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, isfinite

from .circular_segment import CircularSegment
from .linear_segment import LinearSegment
from .types import ScalarProfile


@dataclass(frozen=True, slots=True)
class HelixSample:
    """Helix geometry at one positive profile-travel coordinate."""

    circumferential_displacement: float
    theta: float
    dtheta_dopening: float
    d2theta_dopening2: float
    helix_angle_magnitude: float


@dataclass(frozen=True, slots=True)
class HelixShiftKinematics:
    """
    One helix sample mapped into the common global shift coordinate.

    The underlying profile uses positive secondary-opening travel ``q``.  The
    caller supplies the known geometry map:

        q = q(s),
        dq_ds = dq / ds,
        d2q_ds2 = d2q / ds2.

    The returned values then provide the quantities needed consistently by
    both the secondary actuator and the later secondary rotational row:

        H  = dtheta / ds,
        H' = d2theta / ds2.

    This is geometry/kinematics only.  It contains no spring, torque, force,
    or inertia quantities.
    """

    opening_travel: float
    d_opening_ds: float
    d2_opening_ds2: float

    circumferential_displacement: float
    theta: float
    dtheta_dopening: float
    d2theta_dopening2: float
    helix_angle_magnitude: float

    dtheta_ds: float
    d2theta_ds2: float


@dataclass(frozen=True, slots=True)
class HelixProfile:
    """
    Torque-reactive helix geometry parameterized by a positive profile travel ``q``.

    The mounted :class:`HelicalPulleyCoupling` maps the pulley-local axial
    coordinate ``x`` into ``q``. The profile itself returns the relative angle
    with the rotational sign used by the shaft equations. For the conventional
    secondary mapping ``q = -x``, opening increases ``q`` while the movable
    sheave rotates in negative relative angle, so ``dtheta/dx > 0`` as in the
    formulation. A primary mounting can reverse the signed q(x) mapping to
    represent the opposite helix handedness without changing the force law.

    Torsional-spring preload belongs separately in
    :class:`HelicalTorqueReactionSpec`; the helix profile itself has no
    clocking offset.
    """

    circumferential_profile: ScalarProfile
    radius: float

    def __post_init__(self) -> None:
        if not isfinite(self.radius) or self.radius <= 0.0:
            raise ValueError("radius must be finite and positive.")

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
                "A torque-reactive helix profile requires positive "
                "circumferential slope du/dq."
            )

        # q is a positive geometric travel coordinate, not the signed relative
        # sheave angle. With the rotational convention used by the formulation,
        # conventional secondary opening rotates the movable member negatively.
        return HelixSample(
            circumferential_displacement=profile.value,
            theta=-profile.value / self.radius,
            dtheta_dopening=-profile.first_derivative / self.radius,
            d2theta_dopening2=-profile.second_derivative / self.radius,
            helix_angle_magnitude=atan2(
                1.0,
                profile.first_derivative,
            ),
        )

    def evaluate_shift_kinematics(
        self,
        *,
        opening_travel: float,
        d_opening_ds: float,
        d2_opening_ds2: float,
    ) -> HelixShiftKinematics:
        """
        Evaluate the helix and map its derivatives to a common shift s.

        The chain rule is:

            dtheta_ds
              = (dtheta/dq) (dq/ds),

            d2theta_ds2
              = (d2theta/dq2) (dq/ds)^2
                + (dtheta/dq) (d2q/ds2).

        Keeping this conversion here ensures that the actuator and future
        rotational row use the same helix kinematics.
        """

        _require_finite("opening_travel", opening_travel)
        _require_finite("d_opening_ds", d_opening_ds)
        _require_finite("d2_opening_ds2", d2_opening_ds2)

        sample = self.evaluate(opening_travel)

        dtheta_ds = sample.dtheta_dopening * d_opening_ds
        d2theta_ds2 = (
            sample.d2theta_dopening2 * d_opening_ds**2
            + sample.dtheta_dopening * d2_opening_ds2
        )

        return HelixShiftKinematics(
            opening_travel=opening_travel,
            d_opening_ds=d_opening_ds,
            d2_opening_ds2=d2_opening_ds2,
            circumferential_displacement=sample.circumferential_displacement,
            theta=sample.theta,
            dtheta_dopening=sample.dtheta_dopening,
            d2theta_dopening2=sample.d2theta_dopening2,
            helix_angle_magnitude=sample.helix_angle_magnitude,
            dtheta_ds=dtheta_ds,
            d2theta_ds2=d2theta_ds2,
        )


def linear_helix_segment(
    *,
    length: float,
    helix_angle_degrees: float,
) -> LinearSegment:
    """
    Build one conventional torque-reactive helix segment.

    The helix angle beta is measured from the circumferential direction.
    Positive opening travel q therefore gives:

        du/dq = cot(beta) > 0.

    There is intentionally no handedness parameter: CINDER's helix convention
    is the ordinary torque-reactive orientation in which opening winds the
    spring further and forward torque adds local clamping force.
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
        raise ValueError("helix_angle_degrees must lie strictly between 0 and 90.")


def _require_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")
