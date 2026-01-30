from cvt_simulator.models.ramps.ramp_segment import RampSegment
import numpy as np
import math


class CircularSegment(RampSegment):
    """
    Circular arc segment parameterized by slope angles and quadrant.

    The quadrant determines the curve orientation:
    - Q1 (top-right): Negative slopes curving from steep down to gentle down
    - Q2 (top-left): Positive slopes curving from gentle up to steep up
    - Q3 (bottom-left): Negative slopes curving from gentle down to steep down
    - Q4 (bottom-right): Positive slopes curving from steep up to gentle up

    Slopes are always specified as POSITIVE values (magnitude only).
    The quadrant determines the actual sign.
    """

    def __init__(
        self,
        length: float,
        angle_start: float,
        angle_end: float,
        quadrant: int = 3,
    ):
        """
        :param length: Horizontal length of the segment
        :param angle_start: Starting slope angle in degrees (POSITIVE, e.g., 45 for slope magnitude 1)
        :param angle_end: Ending slope angle in degrees (POSITIVE)
        :param quadrant: Which quadrant (1-4). Q1&Q3 give negative slopes, Q2&Q4 give positive slopes
        """
        super().__init__(length)

        if quadrant not in [1, 2, 3, 4]:
            raise ValueError("quadrant must be 1, 2, 3, or 4")

        if angle_start < 0:
            raise ValueError(
                f"angle_start must be positive (magnitude only), got {angle_start}. "
                f"The quadrant parameter determines the sign of slopes. "
                f"Use abs({angle_start}) = {abs(angle_start)} and quadrant={quadrant}"
            )

        if angle_end < 0:
            raise ValueError(
                f"angle_end must be positive (magnitude only), got {angle_end}. "
                f"The quadrant parameter determines the sign of slopes. "
                f"Use abs({angle_end}) = {abs(angle_end)} and quadrant={quadrant}"
            )

        if angle_start > 90:
            raise ValueError(
                f"angle_start must be between 0 and 90 degrees, got {angle_start}°"
            )

        if angle_end > 90:
            raise ValueError(
                f"angle_end must be between 0 and 90 degrees, got {angle_end}°"
            )

        # Force angles to be positive (magnitude only)
        angle_start = abs(angle_start)
        angle_end = abs(angle_end)

        # Validate angle ordering based on quadrant
        # Q1 & Q3: angles should decrease (steep to gentle, going around the quadrant)
        # Q2 & Q4: angles should increase (gentle to steep, going around the quadrant)
        if quadrant in [1, 3]:
            if angle_start < angle_end:
                raise ValueError(
                    f"In quadrant {quadrant}, angle_start ({angle_start}°) must be >= angle_end ({angle_end}°). "
                    f"The arc should go from steep to gentle (e.g., 89° to 1°)."
                )
        else:  # quadrant in [2, 4]
            if angle_start > angle_end:
                raise ValueError(
                    f"In quadrant {quadrant}, angle_start ({angle_start}°) must be <= angle_end ({angle_end}°). "
                    f"The arc should go from gentle to steep (e.g., 1° to 89°)."
                )

        # Store original parameters
        self.angle_start = angle_start
        self.angle_end = angle_end
        self.quadrant = quadrant

        # Convert to radians
        angle_start_rad = math.radians(angle_start)
        angle_end_rad = math.radians(angle_end)

        # For a circle, the tangent slope at position angle θ is: slope = -cot(θ) = -cos(θ)/sin(θ)
        # Given slope angle α where |slope| = tan(α), we solve for θ
        # The mapping depends on the quadrant

        self.theta_start = self._slope_angle_to_position_angle(
            angle_start_rad, quadrant
        )
        self.theta_end = self._slope_angle_to_position_angle(angle_end_rad, quadrant)

        # Calculate radius from horizontal length
        # Δx = r * (cos(θ_end) - cos(θ_start))
        cos_diff = math.cos(self.theta_end) - math.cos(self.theta_start)

        if abs(cos_diff) < 1e-10:
            raise ValueError("angle_start and angle_end produce no horizontal change")

        self.radius = abs(length / cos_diff)

        # Circle center position (offset from origin)
        self.cx = -self.radius * math.cos(self.theta_start)
        self.cy = -self.radius * math.sin(self.theta_start)

    def _slope_angle_to_position_angle(
        self, slope_angle_rad: float, quadrant: int
    ) -> float:
        """
        Convert a slope angle to position angle on the circle.

        For a circle centered at origin, the tangent slope at position θ is: slope = -cot(θ)
        Given slope angle α where slope = tan(α), we have: tan(α) = -cot(θ)

        Key mappings:
        - 90° slope (vertical): θ at 0° or 180° (right or left of circle)
        - 0° slope (horizontal): θ at 90° or 270° (top or bottom of circle)

        Quadrant meanings:
        - Q1 (0 to π/2): Top right, negative slopes, θ from 0 to π/2
        - Q2 (π/2 to π): Top left, positive slopes, θ from π/2 to π
        - Q3 (π to 3π/2): Bottom left, negative slopes, θ from π to 3π/2
        - Q4 (3π/2 to 2π): Bottom right, positive slopes, θ from 3π/2 to 2π
        """
        # For a circle, if the tangent slope is tan(α), then:
        # dy/dx = -cot(θ) = tan(α)
        # cot(θ) = -tan(α)
        # tan(θ) = -1/tan(α) = -cot(α)
        # θ = arctan(-cot(α))

        # Alternatively, for slope angle α:
        # At slope angle 0° (horizontal), position is at π/2 or 3π/2 (top or bottom)
        # At slope angle 90° (vertical), position is at 0 or π (right or left)

        # The relationship is: θ = π/2 - α for the base angle
        # Then we add quadrant offset

        quadrant_offsets = {
            1: 0,  # Q1: 0 to π/2
            2: np.pi / 2,  # Q2: π/2 to π
            3: np.pi,  # Q3: π to 3π/2
            4: 3 * np.pi / 2,  # Q4: 3π/2 to 2π
        }

        # Within each quadrant, as slope angle goes from 90° to 0°,
        # position angle goes from quadrant_start to quadrant_end
        # So: θ = quadrant_offset + (π/2 - α)

        base_angle = np.pi / 2 - slope_angle_rad

        return quadrant_offsets[quadrant] + base_angle

    def height(self, x: float) -> float:
        """Calculate y-coordinate at position x along the arc."""
        # Calculate position angle from x coordinate
        # For a circle: x = cx + r*cos(θ)
        # So: cos(θ) = (x - x_start)/r + cos(θ_start)

        x_rel = x - self.x_start
        cos_theta = x_rel / self.radius + math.cos(self.theta_start)

        # Clamp to valid range for arccos
        cos_theta = max(-1.0, min(1.0, cos_theta))

        # Find theta from cos(theta), considering the quadrant
        # arccos returns [0, π], we need to map to the correct quadrant
        if self.quadrant in [1, 2]:
            # Upper half of circle: θ ∈ [0, π]
            theta = math.acos(cos_theta)
        else:
            # Lower half of circle: θ ∈ [π, 2π]
            theta = 2 * math.pi - math.acos(cos_theta)

        # Calculate position on circle
        y = self.cy + self.radius * math.sin(theta)

        # Offset to start at y_start
        y_offset = self.cy + self.radius * math.sin(self.theta_start)
        return y - y_offset + self.y_start

    def slope(self, x: float) -> float:
        """Calculate slope (dy/dx) at position x along the arc."""
        # Calculate position angle from x coordinate (same as in height method)
        x_rel = x - self.x_start
        cos_theta = x_rel / self.radius + math.cos(self.theta_start)
        cos_theta = max(-1.0, min(1.0, cos_theta))

        if self.quadrant in [1, 2]:
            theta = math.acos(cos_theta)
        else:
            theta = 2 * math.pi - math.acos(cos_theta)

        # Slope on circle: dy/dx = (dy/dθ)/(dx/dθ) = (r*cos(θ))/(-r*sin(θ)) = -cot(θ)
        slope = -math.cos(theta) / math.sin(theta)

        return slope

    def inverse_height(self, y: float) -> float:
        """Given a height y, find the x position that produces that height.

        For a circle: (x - cx)² + (y - cy)² = r²
        Solving for x: x = cx ± sqrt(r² - (y - cy)²)

        Args:
            y: Target height (adjusted for segment's y_start)

        Returns:
            x position that produces the given height

        Raises:
            ValueError: If y is outside circle radius, produces ambiguous solutions,
                       or no solutions fall within segment bounds
        """
        # Adjust y for segment offset
        y_adjusted = y - self.y_start

        # Calculate y position in circle coordinates
        y_circle = y_adjusted + (self.cy + self.radius * math.sin(self.theta_start))

        # Check if y is within circle radius
        discriminant = self.radius**2 - (y_circle - self.cy) ** 2

        if discriminant < 0:
            raise ValueError(
                f"Height y={y} is outside circle radius. "
                f"Circle vertical range: [{self.cy - self.radius}, {self.cy + self.radius}]"
            )

        # Two possible x solutions
        sqrt_term = math.sqrt(discriminant)
        x1 = self.cx + sqrt_term
        x2 = self.cx - sqrt_term

        # Check which solutions fall within segment bounds
        x1_valid = self.x_start <= x1 <= self.x_end
        x2_valid = self.x_start <= x2 <= self.x_end

        if x1_valid and x2_valid:
            raise ValueError(
                f"Height y={y} produces ambiguous solutions: x={x1} and x={x2}. "
                f"Both are within segment range [{self.x_start}, {self.x_end}]. "
                f"This circular segment spans too much of the circle to invert uniquely."
            )
        elif x1_valid:
            return x1
        elif x2_valid:
            return x2
        else:
            raise ValueError(
                f"Height y={y} corresponds to x positions {x1} and {x2}, "
                f"but neither falls within segment range [{self.x_start}, {self.x_end}]"
            )
