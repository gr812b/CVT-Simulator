from matplotlib import pyplot as plt
import numpy as np
import ezdxf


def visualize_ramps(ramps):
    """
    Visualizes the ramp profiles for height, slope, and angle as three separate graphs.
    The height graph is displayed with an equal aspect ratio.

    :param ramps: A list of ramp objects. Each ramp should have a .segments attribute,
                  and each segment must support .height(x) and .slope(x) methods.
    """

    # Helper function to determine style based on segment type.
    def get_segment_style(segment):
        if hasattr(segment, "__class__"):
            if segment.__class__.__name__ == "LinearSegment":
                return "blue", "Linear"
            elif segment.__class__.__name__ == "EulerSpiralSegment":
                return "red", "Euler Spiral"
            elif (
                segment.__class__.__name__ == "CubicSpiralZeroZero"
                or segment.__class__.__name__ == "CubicSpiralZeroK1"
            ):
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
    plot_attribute(
        lambda seg, x: seg.height(x),
        "Height",
        "Height Profile by Segment",
        equal_aspect=True,
    )

    # Plot Slope Profile.
    plot_attribute(
        lambda seg, x: seg.slope(x),
        "Slope (dy/dx)",
        "Slope Profile by Segment",
        equal_aspect=False,
    )

    # Plot Angle Profile (angle computed as arctan(slope)).
    plot_attribute(
        lambda seg, x: np.arctan(seg.slope(x)),
        "Angle (radians)",
        "Angle Profile by Segment",
        equal_aspect=False,
    )

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
    doc = ezdxf.new(dxfversion="R2010")
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
