class RampSegment:
    """Base class for ramp segments."""

    def __init__(self, length: float):
        self.length = length
        self.x_start = 0.0  # Will be set by PiecewiseRamp
        self.x_end = length  # Will be adjusted by PiecewiseRamp
        self.y_start = None  # Will be set automatically

    def height(self, x: float) -> float:
        """Returns height at given x."""
        raise NotImplementedError

    def slope(self, x: float) -> float:
        """Returns derivative (slope) at given x."""
        raise NotImplementedError
