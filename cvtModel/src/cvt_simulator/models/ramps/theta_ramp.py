"""
Theta ramp wrapper for helix cam geometry.

Input convention:
- The provided PiecewiseRamp segment angles are interpreted as helix angles
    measured from the circumferential direction.

Internal convention:
- The internal PiecewiseRamp stores circumferential displacement u(x), where u
    is the distance the cam surface moves as you move axially.

The rotation angle is:
        theta(x) = u(x) / r_helix

where r_helix is the helix radius.
"""

import math
from cvt_simulator.models.ramps.piecewise_ramp import PiecewiseRamp
from cvt_simulator.models.ramps.linear_segment import LinearSegment
from cvt_simulator.models.ramps.circular_segment import CircularSegment


class ThetaRamp:
    """
    Wraps a PiecewiseRamp of helix angles and converts it to u(x).

    The input ramp segment angles are helix angles measured from the
    circumferential direction. ThetaRamp converts each segment to an equivalent
    displacement-slope ramp and stores that internal representation as u(x).

    From this:
    - theta(x) = u(x) / r (direct, no integration needed)
    - dtheta/dx = (du/dx) / r = slope(x) / r

    where r is the helix radius [m].
    """

    def __init__(self, angle_ramp: PiecewiseRamp, helix_radius: float):
        """
        Initialize theta ramp wrapper.

        Args:
            angle_ramp: PiecewiseRamp whose segment angles are helix angles
                from circumferential direction [deg]
            helix_radius: Helix radius r [m]
        """
        if helix_radius <= 0:
            raise ValueError(f"helix_radius must be positive, got {helix_radius}")

        self.angle_ramp = self._convert_helix_angle_ramp_to_u_ramp(angle_ramp)
        self.r = helix_radius

    @staticmethod
    def _helix_angle_to_slope_angle(helix_angle_deg: float) -> float:
        """
        Convert helix angle (from circumferential direction) to slope angle.

        Uses:
            du/dx = cot(beta)
            slope_angle = atan(du/dx)
        where beta is the helix angle.
        """
        beta_rad = math.radians(helix_angle_deg)
        tan_beta = math.tan(beta_rad)
        if abs(tan_beta) < 1e-12:
            raise ValueError(
                "Helix angle is too close to 0°/180°; cot(beta) is singular"
            )
        return math.degrees(math.atan(1.0 / tan_beta))

    @classmethod
    def _convert_helix_angle_ramp_to_u_ramp(cls, helix_angle_ramp: PiecewiseRamp) -> PiecewiseRamp:
        """Convert a helix-angle piecewise ramp into a displacement-slope ramp."""
        converted_ramp = PiecewiseRamp()

        for segment in helix_angle_ramp.segments:
            if isinstance(segment, LinearSegment):
                converted_ramp.add_segment(
                    LinearSegment(
                        length=segment.length,
                        angle=cls._helix_angle_to_slope_angle(segment.angle),
                    )
                )
                continue

            if isinstance(segment, CircularSegment):
                converted_ramp.add_segment(
                    CircularSegment(
                        length=segment.length,
                        angle_start=cls._helix_angle_to_slope_angle(segment.angle_start),
                        angle_end=cls._helix_angle_to_slope_angle(segment.angle_end),
                        quadrant=segment.quadrant,
                    )
                )
                continue

            raise TypeError(
                f"Unsupported ramp segment type for ThetaRamp conversion: {type(segment).__name__}"
            )

        return converted_ramp

    def theta(self, x: float) -> float:
        """
        Get cam rotation angle at axial position x.

        Args:
            x: Axial position [m]

        Returns:
            Rotation angle [rad]
        """
        u = self.angle_ramp.height(x)
        return u / self.r

    def dtheta_dx(self, x: float) -> float:
        """
        Get derivative dθ/dx at position x.

        Args:
            x: Axial position [m]

        Returns:
            Rotation rate [rad/m]
        """
        du_dx = self.angle_ramp.slope(x)
        return du_dx / self.r

    def angle_multiplier(self, x: float) -> float:
        """
        Get angle-only contribution: du/dx.

        Provides the angle-independent part in:
            dθ/dx = angle_multiplier(x) / r

        Args:
            x: Axial position [m]

        Returns:
            du/dx [m/m = dimensionless]
        """
        return self.angle_ramp.slope(x)

    def helix_angle_rad(self, x: float) -> float:
        """
        Get helix angle at x [rad].

        The helix angle alpha is defined by:
            tan(alpha) = 1 / (r * dtheta/dx) = 1 / du/dx

        Args:
            x: Axial position [m]

        Returns:
            Helix angle [rad]
        """
        du_dx = self.angle_ramp.slope(x)
        if abs(du_dx) < 1e-12:
            raise ValueError("du/dx is near zero; helix angle is singular")
        return math.atan(1.0 / du_dx)

    def helix_angle_deg(self, x: float) -> float:
        """Get helix angle at x [deg]."""
        return math.degrees(self.helix_angle_rad(x))

    def get_x_range(self) -> tuple[float, float]:
        """Get the axial range [x_min, x_max] of the ramp."""
        if not self.angle_ramp.segments:
            raise ValueError("Ramp has no segments")
        x_min = self.angle_ramp.segments[0].x_start
        x_max = self.angle_ramp.segments[-1].x_end
        return x_min, x_max

    def get_theta_range(self) -> tuple[float, float]:
        """Get the rotation range [θ_min, θ_max] of the ramp."""
        x_min, x_max = self.get_x_range()
        theta_min = self.theta(x_min)
        theta_max = self.theta(x_max)
        return min(theta_min, theta_max), max(theta_min, theta_max)
