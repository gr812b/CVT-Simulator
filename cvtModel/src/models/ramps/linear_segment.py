from models.ramps.ramp_segment import RampSegment


class LinearSegment(RampSegment):
    """Linear segment: y = mx"""

    def __init__(self, x_start: float, x_end: float, slope: float):
        super().__init__(x_start, x_end)
        self.m = slope

    def height(self, x: float) -> float:
        return self.m * (x - self.x_start) + self.y_start

    def slope(self, x: float) -> float:
        return self.m
