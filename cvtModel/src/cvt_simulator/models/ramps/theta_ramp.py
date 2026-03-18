"""
Theta ramp wrapper for helix cam geometry.

The piecewise ramp stores circumferential displacement u(x), where u is the
distance the cam surface moves (in mm or meters) as you move axially.

The rotation angle is then simply:
    theta(x) = u(x) / r_helix

where r_helix is the radius of the helix (constant).
"""

import math
from cvt_simulator.models.ramps.piecewise_ramp import PiecewiseRamp


class ThetaRamp:
    """
    Wraps a PiecewiseRamp that defines circumferential displacement u(x).

    The internal ramp stores u(x) (e.g., in meters), where u is the axial
    progression of the cam surface around the helix.

    From this:
    - theta(x) = u(x) / r (direct, no integration needed)
    - dtheta/dx = (du/dx) / r = slope(x) / r

    where r is the helix radius [m].
    """

    def __init__(self, angle_ramp: PiecewiseRamp, helix_radius: float):
        """
        Initialize theta ramp wrapper.

        Args:
            angle_ramp: PiecewiseRamp storing circumferential displacement u(x)
            helix_radius: Helix radius r [m]
        """
        if helix_radius <= 0:
            raise ValueError(f"helix_radius must be positive, got {helix_radius}")

        self.angle_ramp = angle_ramp
        self.r = helix_radius

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
