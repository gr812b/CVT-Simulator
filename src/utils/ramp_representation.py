import numpy as np
from typing import List
import matplotlib.pyplot as plt
from constants.car_specs import INITIAL_FLYWEIGHT_RADIUS
import math
from scipy.integrate import quad
import ezdxf

from utils.conversions import meter_to_inch


class RampSegment:
    """Base class for ramp segments."""

    def __init__(self, x_start: float, x_end: float):
        self.x_start = x_start
        self.x_end = x_end
        self.y_start = None  # Will be set automatically

    def height(self, x: float) -> float:
        """Returns height at given x."""
        raise NotImplementedError

    def slope(self, x: float) -> float:
        """Returns derivative (slope) at given x."""
        raise NotImplementedError


class LinearSegment(RampSegment):
    """Linear segment: y = mx"""

    def __init__(self, x_start: float, x_end: float, slope: float):
        super().__init__(x_start, x_end)
        self.m = slope

    def height(self, x: float) -> float:
        return self.m * (x - self.x_start) + self.y_start

    def slope(self, x: float) -> float:
        return self.m


class CircularSegment(RampSegment):
    """Circular segment where user defines rotation."""

    def __init__(
        self,
        x_start: float,
        x_end: float,
        radius: float,
        theta_start: float,
        theta_end: float,
    ):
        """
        :param x_start: Start x position
        :param x_end: End x position (automatically inferred)
        :param theta_start: Start angle in radians (from 0 to π/2)
        :param theta_end: End angle in radians (from 0 to π/2)
        """
        super().__init__(x_start, x_end)

        if not (0 <= theta_start <= np.pi / 2):
            raise ValueError("theta_start must be in [0, π/2]")
        if not (0 <= theta_end <= np.pi / 2):
            raise ValueError("theta_end must be in [0, π/2]")
        if theta_start >= theta_end:
            raise ValueError("theta_start must be less than theta_end")

        self.theta_start = np.pi + theta_start
        self.theta_end = np.pi + theta_end
        self.radius = radius

    # Convert from an angle to the x distance from axis
    def angle_to_x(self, theta: float) -> float:
        return self.radius * math.cos(theta)

    # Equation of a circle in the third quadrant
    def f(self, x: float) -> float:
        return -math.sqrt(self.radius**2 - x**2)

    def f_prime(self, x: float) -> float:
        return x / math.sqrt(self.radius**2 - x**2)

    def map_x(self, x: float) -> float:
        start_offset = self.angle_to_x(self.theta_start)
        end_offset = self.angle_to_x(self.theta_end)

        scaled_x = (x - self.x_start) / (self.x_end - self.x_start)
        adjusted_x = start_offset + scaled_x * (end_offset - start_offset)

        return adjusted_x

    def height(self, x: float) -> float:
        """Finds y-coordinate on the circular arc corresponding to x."""
        adjusted_x = self.map_x(x)
        starting_height = self.f(self.angle_to_x(self.theta_start))
        return self.f(adjusted_x) - starting_height + self.y_start

    def slope(self, x: float) -> float:
        """Returns the slope (dy/dx) at position x on the ramp."""
        adjusted_x = self.map_x(x)
        return self.f_prime(adjusted_x)


class ProDefinedSegment(RampSegment):
    def __init__(self, x_start: float, x_end: float, prev_seg_height: float, end_length: float, initial_slope: float, r_initial: float = INITIAL_FLYWEIGHT_RADIUS):
        super().__init__(x_start, x_end)
        self.r_initial = r_initial
        self.end_length = end_length
        self.C = ((2 * r_initial) + prev_seg_height) ** 2 - x_start**2
        self.x_offset = math.sqrt((initial_slope**2 * self.C)/(1 - initial_slope**2))
        # print(f"X offset: {self.x_offset}, F(x_offset): {self.f(self.x_offset)}, F'(x_offset): {self.f_prime(self.x_offset)}")
        # Do the same but pass in x_start + x_offset
        # print(f"X start: {self.x_start}, F(x_start + x_offset): {self.f(self.x_start + self.x_offset)}, F'(x_start + x_offset): {self.f_prime(self.x_start + self.x_offset)}")

    def x_shift(self, x: float) -> float:
        return (x - self.x_start) - self.x_offset

    def f(self, x: float) -> float:
        return (math.sqrt(x**2 + self.C) - self.r_initial)
    
    def f_prime(self, x: float) -> float:
        return (x / math.sqrt(x**2 + self.C))
    
    def height(self, x: float) -> float:
        adjusted_x = self.x_shift(x)
        starting_height = self.f(-self.x_offset)
        return self.f(adjusted_x) - starting_height + self.y_start
    
    def slope(self, x: float) -> float:
        adjusted_x = self.x_shift(x)
        return self.f_prime(adjusted_x)


class EulerSpiralSegment(RampSegment):
    """
    Euler spiral segment that transitions smoothly between two slopes.
    Instead of passing tangent angles, you supply the starting and ending slopes.
    The slopes are converted to tangent angles (θ = arctan(slope)).
    
    This implementation now allows the initial slope to be flatter (e.g. -0.25)
    and the final slope to be steeper (e.g. -10). The tangent angle then decreases 
    along the segment, i.e. theta_start > theta_end.
    """
    def __init__(self, x_start: float, x_end: float, slope_start: float, slope_end: float):
        """
        :param x_start: start horizontal coordinate.
        :param x_end: end horizontal coordinate (defines the horizontal span L).
        :param slope_start: starting slope (e.g. -0.25 for a flat start).
        :param slope_end: ending slope (e.g. -10 for a steep end).
        """
        super().__init__(x_start, x_end)
        # Convert slopes to tangent angles.
        self.theta_start = np.arctan(slope_start)
        self.theta_end = np.arctan(slope_end)
        # Note: for a transition from flatter to steeper (more negative) slope,
        # theta_start > theta_end.
        self.delta = self.theta_end - self.theta_start  # This will be negative.
        
        # Horizontal length of the segment.
        self.L = self.x_end - self.x_start
        
        # Compute the normalization factor:
        # I = ∫₀¹ cos(theta_start + delta*u²) du.
        I, _ = quad(lambda u: np.cos(self.theta_start + self.delta * u**2), 0, 1)
        # Set s_end so that the horizontal projection equals L.
        self.s_end = self.L / I

    def _x_of_s(self, s: float) -> float:
        """Computes the horizontal displacement for a given arc length s."""
        u_upper = s / self.s_end
        integral, _ = quad(lambda u: np.cos(self.theta_start + self.delta * u**2), 0, u_upper)
        return self.s_end * integral

    def _y_of_s(self, s: float) -> float:
        """Computes the vertical displacement for a given arc length s."""
        u_upper = s / self.s_end
        integral, _ = quad(lambda u: np.sin(self.theta_start + self.delta * u**2), 0, u_upper)
        return self.s_end * integral

    def _find_s_for_x(self, x_offset: float, tol: float = 1e-8) -> float:
        """
        Uses binary search to find the arc length s corresponding to a given horizontal offset.
        """
        lower = 0.0
        upper = self.s_end
        while self._x_of_s(upper) < x_offset:
            upper *= 2
        while upper - lower > tol:
            mid = (lower + upper) / 2.0
            if self._x_of_s(mid) < x_offset:
                lower = mid
            else:
                upper = mid
        return (lower + upper) / 2.0

    def height(self, x: float) -> float:
        """
        Returns the vertical height at horizontal position x.
        """
        if not (self.x_start <= x <= self.x_end):
            raise ValueError(f"x={x} is out of the Euler spiral segment range!")
        x_offset = x - self.x_start
        s_val = self._find_s_for_x(x_offset)
        return self.y_start + self._y_of_s(s_val)

    def slope(self, x: float) -> float:
        """
        Returns the slope (dy/dx) at horizontal position x.
        """
        if not (self.x_start <= x <= self.x_end):
            raise ValueError(f"x={x} is out of the Euler spiral segment range!")
        x_offset = x - self.x_start
        s_val = self._find_s_for_x(x_offset)
        # Compute the instantaneous tangent angle:
        angle = self.theta_start + self.delta * (s_val / self.s_end) ** 2
        return math.tan(angle)

class CubicSpiralZeroZero(RampSegment):
    """
    A cubic spiral transition defined by:
    
      θ(s) = θ₀ + B·s² + C·s³,   0 ≤ s ≤ L_eff,
    
    with boundary conditions:
      θ(0)=θ₀,    κ(0)=θ'(0)=0,
      θ(L_eff)=θ₁, κ(L_eff)=θ'(L_eff)=0.
      
    These conditions yield:
      B = 3(θ₁ - θ₀) / L_eff²,     C = -2(θ₁ - θ₀) / L_eff³.
      
    In our implementation, the user specifies x_start and x_end (thus a chord length),
    but because the horizontal projection of the spiral is:
    
      x(L_eff) = ∫₀^(L_eff) cos(θ(s)) ds,
    
    we iterate on L_eff until x(L_eff) matches the chord length exactly.
    """
    def __init__(self, x_start: float, x_end: float, slope_start: float, slope_end: float, tol: float=1e-8):
        super().__init__(x_start, x_end)
        # The desired horizontal chord length.
        chord_target = x_end - x_start

        # Convert slopes to tangent angles.
        self.theta0 = math.atan(slope_start)
        self.theta1 = math.atan(slope_end)
        dtheta = self.theta1 - self.theta0

        # --- Find effective arc length L_eff such that the horizontal projection matches chord_target.
        # Our cubic spiral is defined as:
        #   θ(s) = θ₀ + B s² + C s³,   with B = 3*dθ / L_eff² and C = -2*dθ / L_eff³.
        # Then, horizontal projection is:
        #   x(L_eff) = ∫_0^(L_eff) cos(θ₀ + (3*dθ/L_eff²) s² - (2*dθ/L_eff³) s³) ds.
        # We want: x(L_eff) = chord_target.
        def chord_projection(L_eff):
            B = 3*dtheta / (L_eff**2)
            C = -2*dtheta / (L_eff**3)
            val, _ = quad(lambda u: math.cos(self.theta0 + B*u**2 + C*u**3), 0, L_eff)
            return val

        # Use bisection to solve f(L_eff) = chord_projection(L_eff) - chord_target = 0.
        # Initial guess: For a straight line, L_eff would equal chord_target.
        L_low = chord_target
        L_high = chord_target * 1.5  # a reasonable upper bound
        
        # Ensure that f(L_low) and f(L_high) have opposite signs.
        f_low = chord_projection(L_low) - chord_target
        f_high = chord_projection(L_high) - chord_target

        # In some cases, if dtheta is small, they may both be nearly zero.
        # We'll assume we can find bounds. Otherwise, no iteration is needed.
        while f_low * f_high > 0:
            L_high *= 1.1
            f_high = chord_projection(L_high) - chord_target
        
        # Bisection iteration.
        while abs(L_high - L_low) > tol:
            L_mid = (L_low + L_high) / 2.0
            f_mid = chord_projection(L_mid) - chord_target
            if f_mid * f_low < 0:
                L_high = L_mid
                f_high = f_mid
            else:
                L_low = L_mid
                f_low = f_mid
        L_eff = (L_low + L_high) / 2.0
        self.L = L_eff  # effective arc-length that gives the correct chord

        # Now compute B and C based on L_eff.
        self.B = 3*dtheta/(self.L**2)
        self.C = -2*dtheta/(self.L**3)
        self.delta = dtheta  # total change in angle over the spiral

    def _theta(self, s: float) -> float:
        return self.theta0 + self.B * s**2 + self.C * s**3

    def _x_of_s(self, s: float) -> float:
        val, _ = quad(lambda u: math.cos(self._theta(u)), 0, s)
        return val

    def _y_of_s(self, s: float) -> float:
        val, _ = quad(lambda u: math.sin(self._theta(u)), 0, s)
        return val

    def _find_s_for_x(self, x_offset: float, tol: float = 1e-8) -> float:
        lower, upper = 0.0, self.L
        while self._x_of_s(upper) < x_offset:
            upper *= 2
        while upper - lower > tol:
            mid = (lower + upper) / 2.0
            if self._x_of_s(mid) < x_offset:
                lower = mid
            else:
                upper = mid
        return (lower + upper) / 2.0

    def height(self, x: float) -> float:
        if not (self.x_start <= x <= self.x_end):
            raise ValueError(f"{x} out of range")
        x_offset = x - self.x_start
        s_val = self._find_s_for_x(x_offset)
        return self.y_start + self._y_of_s(s_val)

    def slope(self, x: float) -> float:
        if not (self.x_start <= x <= self.x_end):
            raise ValueError(f"{x} out of range")
        x_offset = x - self.x_start
        s_val = self._find_s_for_x(x_offset)
        return math.tan(self._theta(s_val))
    
class CubicSpiralZeroK1(RampSegment):
    """
    Cubic spiral defined by:
      θ(s) = θ₀ + B s² + C s³,   0 ≤ s ≤ L_eff,
    with:
      θ(0) = θ₀ = arctan(slope_start),
      θ'(0)=0,
      θ(L_eff)=θ₁ = arctan(target_slope),
      θ'(L_eff)=k₁  (target curvature).
    
    The coefficients are given by:
      C = (k₁ L_eff - 2(θ₁-θ₀)) / L_eff³,
      B = -k₁/L_eff + 3(θ₁-θ₀)/L_eff².
    
    Because the horizontal projection of the spiral is
      x(L_eff) = ∫₀^(L_eff) cos(θ(s)) ds,
    we adjust L_eff using bisection so that x(L_eff) equals the given chord length.
    """
    def __init__(self, x_start: float, x_end: float, slope_start: float, slope_end: float, target_curvature: float, tol: float=1e-8):
        super().__init__(x_start, x_end)
        chord_target = x_end - x_start

        self.theta0 = math.atan(slope_start)
        self.theta1 = math.atan(slope_end)
        dtheta = self.theta1 - self.theta0
        self.k1 = target_curvature  # target curvature at end

        # Define a function that, given an effective arc length L_eff, returns the horizontal projection.
        def chord_projection(L_eff):
            B = -self.k1/L_eff + 3*dtheta/(L_eff**2)
            C = (self.k1*L_eff - 2*dtheta)/(L_eff**3)
            val, _ = quad(lambda u: math.cos(self.theta0 + B*u**2 + C*u**3), 0, L_eff)
            return val

        # Use bisection to solve chord_projection(L_eff) = chord_target.
        L_low = chord_target
        L_high = chord_target * 1.5
        f_low = chord_projection(L_low) - chord_target
        f_high = chord_projection(L_high) - chord_target
        while f_low * f_high > 0:
            L_high *= 1.1
            f_high = chord_projection(L_high) - chord_target
        while abs(L_high - L_low) > tol:
            L_mid = (L_low + L_high)/2.0
            f_mid = chord_projection(L_mid) - chord_target
            if f_mid * f_low < 0:
                L_high = L_mid
                f_high = f_mid
            else:
                L_low = L_mid
                f_low = f_mid
        L_eff = (L_low + L_high)/2.0
        self.L = L_eff  # effective arc length for the spiral
        
        # Now set coefficients B and C using the formulas:
        self.B = -self.k1/self.L + 3*dtheta/(self.L**2)
        self.C = (self.k1*self.L - 2*dtheta)/(self.L**3)
        self.delta = dtheta

    def _theta(self, s: float) -> float:
        return self.theta0 + self.B*s**2 + self.C*s**3

    def _x_of_s(self, s: float) -> float:
        val, _ = quad(lambda u: math.cos(self._theta(u)), 0, s)
        return val

    def _y_of_s(self, s: float) -> float:
        val, _ = quad(lambda u: math.sin(self._theta(u)), 0, s)
        return val

    def _find_s_for_x(self, x_offset: float, tol: float=1e-8) -> float:
        lower, upper = 0.0, self.L
        while self._x_of_s(upper) < x_offset:
            upper *= 2
        while upper-lower > tol:
            mid = (lower+upper)/2.0
            if self._x_of_s(mid) < x_offset:
                lower = mid
            else:
                upper = mid
        return (lower+upper)/2.0

    def height(self, x: float) -> float:
        if not (self.x_start <= x <= self.x_end):
            raise ValueError(f"{x} out of range")
        x_offset = x - self.x_start
        s_val = self._find_s_for_x(x_offset)
        return self.y_start + self._y_of_s(s_val)

    def slope(self, x: float) -> float:
        if not (self.x_start <= x <= self.x_end):
            raise ValueError(f"{x} out of range")
        x_offset = x - self.x_start
        s_val = self._find_s_for_x(x_offset)
        return math.tan(self._theta(s_val))

class PiecewiseRamp:
    """Handles multiple ramp segments and ensures continuity automatically."""

    def __init__(self):
        self.segments: List[RampSegment] = []

    def add_segment(self, segment: RampSegment):
        """Adds a new segment and ensures continuity with previous ones."""
        if self.segments:
            prev_segment = self.segments[-1]
            prev_y_end = prev_segment.height(prev_segment.x_end)
            segment.y_start = prev_y_end  # Auto-connect
        else:
            segment.y_start = 0  # Default start height

        self.segments.append(segment)

    def height(self, x: float) -> float:
        """Computes the height at x, ensuring continuity dynamically."""
        for segment in self.segments:
            if segment.x_start <= x <= segment.x_end:
                return abs(segment.height(x))
        raise ValueError(f"x={x} is out of ramp range!")

    def slope(self, x: float) -> float:
        """Finds the appropriate segment and computes slope."""
        for segment in self.segments:
            if segment.x_start <= x <= segment.x_end:
                return abs(segment.slope(x))
        raise ValueError(f"x={x} is out of ramp range!")


def visualize_ramps(ramps):
    """
    Visualizes the ramp profiles for height, slope, and angle as three separate graphs.
    The height graph is displayed with an equal aspect ratio.
    
    :param ramps: A list of ramp objects. Each ramp should have a .segments attribute,
                  and each segment must support .height(x) and .slope(x) methods.
    """
    # Helper function to determine style based on segment type.
    def get_segment_style(segment):
        if hasattr(segment, '__class__'):
            if segment.__class__.__name__ == "LinearSegment":
                return "blue", "Linear"
            elif segment.__class__.__name__ == "EulerSpiralSegment":
                return "red", "Euler Spiral"
            elif segment.__class__.__name__ == "CubicSpiralZeroZero" or segment.__class__.__name__ == "CubicSpiralZeroK1":
                return "orange", "Cubic Spiral"
            elif segment.__class__.__name__ == "CircularSegment":
                return "green", "Circular"
        # Default for other types:
        return "black", type(segment).__name__
    
    # Generic helper to plot a given attribute for all ramp segments.
    def plot_attribute(attribute_func, ylabel, title, equal_aspect=False):
        plt.figure()
        used_labels = set()
        for ramp in ramps:
            for segment in ramp.segments:
                x_vals = np.linspace(segment.x_start, segment.x_end, 2000)
                y_vals = [attribute_func(segment, x) for x in x_vals]
                color, label = get_segment_style(segment)
                if label in used_labels:
                    label = None
                else:
                    used_labels.add(label)
                plt.plot(x_vals, y_vals, color=color, label=label)
        plt.xlabel("X Position")
        plt.ylabel(ylabel)
        plt.title(title)
        plt.grid(True)
        if equal_aspect:
            plt.gca().set_aspect("equal", adjustable="box")
        plt.legend()
    
    # Plot Height Profile (equal aspect ratio).
    plot_attribute(lambda seg, x: seg.height(x), "Height", "Height Profile by Segment", equal_aspect=True)
    
    # Plot Slope Profile.
    plot_attribute(lambda seg, x: seg.slope(x), "Slope (dy/dx)", "Slope Profile by Segment", equal_aspect=False)
    
    # Plot Angle Profile (angle computed as arctan(slope)).
    plot_attribute(lambda seg, x: np.arctan(seg.slope(x)), "Angle (radians)", "Angle Profile by Segment", equal_aspect=False)
    
    plt.show()


def save_ramp_to_dxf(ramp, filename="ramp_profile.dxf", points_per_segment=2000):
    """
    Saves the ramp profile to a DXF file.
    For each ramp segment, this function computes high-resolution (x, y) points,
    adds them as a polyline to the DXF document, and then adds extra connection lines.
    
    The extra connection lines include:
      1. A vertical line dropping exactly 0.750 (units) from the first point.
      2. A horizontal line from the dropped level at the first point's x
         to the last point's x.
      3. A vertical line rising from that horizontal line up to the last point.
    """
    doc = ezdxf.new(dxfversion='R2010')
    msp = doc.modelspace()

    # Collect points from all ramp segments.
    all_points = []
    for segment in ramp.segments:
        x_vals = np.linspace(segment.x_start, segment.x_end, points_per_segment)
        for x in x_vals:
            y = segment.height(x)
            all_points.append((x, y))

    # Add polyline (or individual points if only one exists)
    if len(all_points) > 1:
        msp.add_lwpolyline(all_points)
    else:
        for pt in all_points:
            msp.add_point(pt)

    # Add extra connection lines with a fixed vertical drop of 0.750 (units)
    if len(all_points) >= 2:
        drop = 0.750  # Fixed vertical drop value (in same units as your data)
        first_point = all_points[0]
        last_point = all_points[-1]

        # Intermediate points:
        # 1. Drop vertically from the first point by 0.750.
        intermediate1 = (first_point[0], first_point[1] - drop)
        # 2. Horizontal move: from first point's x to last point's x at the dropped level.
        intermediate2 = (last_point[0], first_point[1] - drop)

        msp.add_line(first_point, intermediate1)
        msp.add_line(intermediate1, intermediate2)
        msp.add_line(intermediate2, last_point)

    doc.saveas(filename)
    print(f"DXF file saved as {filename}")


if __name__ == "__main__":
    length = 1.125
    curveLength = 0.025
    linearLength = 0.18126

    ogLine = LinearSegment(x_start=0, x_end=linearLength, slope=math.tan(math.radians(-15)))
    ogCircle = CircularSegment(
        x_start=ogLine.x_end, # + curveLength
        x_end=length,
        radius=5,
        theta_start=0.985378117709,
        theta_end=1.1984521248,
    )
    ogRamp = PiecewiseRamp()
    ogRamp.add_segment(ogLine)
    ogRamp.add_segment(ogCircle)

    # save_ramp_to_dxf(ogRamp, filename="og_ramp_profile.dxf")
    # visualize_ramps([ogRamp])

    line = LinearSegment(x_start=0, x_end=linearLength, slope=math.tan(math.radians(-15)))
    circle = CircularSegment(
        x_start=line.x_end + curveLength,
        x_end=length,
        radius=5,
        theta_start=0.985378117709,
        theta_end=1.1984521248,
    )
    cubicCircleLine = CubicSpiralZeroK1(
        x_start=line.x_end,
        x_end=line.x_end + curveLength,
        slope_start=line.slope(line.x_end),
        slope_end=circle.slope(circle.x_start),
        target_curvature=1/circle.radius,
    )

    ramp = PiecewiseRamp()
    ramp.add_segment(line)

    proSeg = ProDefinedSegment(
        x_start=line.x_end,
        x_end=length,
        prev_seg_height=ramp.height(line.x_end),
        end_length=length,
        initial_slope=ogCircle.slope(line.x_end),
        r_initial=meter_to_inch(INITIAL_FLYWEIGHT_RADIUS),
    )

    ramp.add_segment(proSeg)

    pro_ramp_list = []

    initial_x_dist = -3.52553
    slope_stuff = [-0.5, 0, 0.5, 1, 1.5, 2, 2.5]

    for x_dist in slope_stuff:
        slope = proSeg.slope(proSeg.x_start + x_dist)
        new_ramp = PiecewiseRamp()
        # Recreate the same line segment.
        new_line = LinearSegment(x_start=0, x_end=linearLength, slope=math.tan(math.radians(-15)))
        new_ramp.add_segment(new_line)
        new_pro_seg = ProDefinedSegment(
            x_start=new_line.x_end,
            x_end=length,
            prev_seg_height=new_ramp.height(new_line.x_end),
            end_length=length,
            initial_slope=slope,
            r_initial=meter_to_inch(INITIAL_FLYWEIGHT_RADIUS),
        )
        new_ramp.add_segment(new_pro_seg)
        pro_ramp_list.append(new_ramp)
        # Save to dxf
        save_ramp_to_dxf(new_ramp, filename=f"pro_ramp_profile_{x_dist}.dxf")
    
    # Visualize all the pro-segment variants.
    visualize_ramps([ogRamp] + pro_ramp_list)


    