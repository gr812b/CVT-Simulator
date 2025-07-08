import math
from constants.car_specs import INITIAL_FLYWEIGHT_RADIUS
from utils.conversions import meter_to_inch
from utils.ramps.circular_segment import CircularSegment
from utils.ramps.cubic_spiral_zero_k1 import CubicSpiralZeroK1
from utils.ramps.linear_segment import LinearSegment
from utils.ramps.piecewise_ramp import PiecewiseRamp
from utils.ramps.pro_defined_segment import ProDefinedSegment
from utils.ramps.ramp_utils import save_ramp_to_dxf, visualize_ramps

## TODO: Remove this file once we extract some of the useful ramps from it

if __name__ == "__main__":

    # Fixed ramp parameters.
    length = 1.125
    linearLength = 0.18126
    # Using a fixed initial linear slope of -15° (downward ramp).
    fixed_angle_deg = 15

    # Define a list of curve lengths (horizontal span of the cubic spiral segment) to test.
    curve_lengths = [0.005, 0.015, 0.040, 0.1]

    ramps_list = []  # To collect ramps for visualization.

    for curve_length in curve_lengths:
        ramp = PiecewiseRamp()

        # Create and add the linear segment.
        linear_seg = LinearSegment(
            x_start=0,
            x_end=linearLength,
            slope=math.tan(math.radians(-fixed_angle_deg)),
        )
        ramp.add_segment(linear_seg)

        # Create the circular segment.
        # It starts right after the cubic spiral, at x = linearLength + curve_length.
        circular_seg = CircularSegment(
            x_start=linear_seg.x_end + curve_length,
            x_end=length,
            radius=5,
            theta_start=0.985378117709,
            theta_end=1.1984521248,
        )
        # Note: We do not need to set circular_seg.y_start because slope calculations do not use it.

        # Create the cubic spiral segment (cubicCircleLine) connecting the linear and circular segments.
        cubicCircleLine = CubicSpiralZeroK1(
            x_start=linear_seg.x_end,
            x_end=linear_seg.x_end + curve_length,
            slope_start=linear_seg.slope(linear_seg.x_end),
            slope_end=circular_seg.slope(circular_seg.x_start),
            target_curvature=1 / circular_seg.radius,
        )

        # Add the cubic spiral segment and the circular segment to the ramp.
        ramp.add_segment(cubicCircleLine)
        ramp.add_segment(circular_seg)

        # Save ramp to DXF file with a filename indicating the curve length.
        dxf_filename = f"ramp_profile_curve_{curve_length:.3f}.dxf"
        save_ramp_to_dxf(ramp, filename=dxf_filename)

        ramps_list.append(ramp)

    # Visualize all ramps together.
    visualize_ramps(ramps_list)


def generateCoolRamps():
    length = 1.125
    # curveLength = 0.025
    linearLength = 0.18126

    ogLine = LinearSegment(
        x_start=0, x_end=linearLength, slope=math.tan(math.radians(-15))
    )
    ogCircle = CircularSegment(
        x_start=ogLine.x_end,  # + curveLength
        x_end=length,
        radius=5,
        theta_start=0.985378117709,
        theta_end=1.1984521248,
    )
    ogRamp = PiecewiseRamp()
    ogRamp.add_segment(ogLine)
    ogRamp.add_segment(ogCircle)

    line = LinearSegment(
        x_start=0, x_end=linearLength, slope=math.tan(math.radians(-15))
    )

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

    slope_stuff = [-0.5, 0, 0.5, 1, 1.5, 2, 2.5]

    for x_dist in slope_stuff:
        slope = proSeg.slope(proSeg.x_start + x_dist)
        new_ramp = PiecewiseRamp()
        # Recreate the same line segment.
        new_line = LinearSegment(
            x_start=0, x_end=linearLength, slope=math.tan(math.radians(-15))
        )
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
