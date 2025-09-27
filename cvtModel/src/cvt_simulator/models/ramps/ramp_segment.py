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
