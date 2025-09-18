import math
from constants.car_specs import INITIAL_FLYWEIGHT_RADIUS
from models.ramps.ramp_segment import RampSegment


class ProDefinedSegment(RampSegment):
    def __init__(
        self,
        x_start: float,
        x_end: float,
        prev_seg_height: float,
        end_length: float,
        initial_slope: float,
        r_initial: float = INITIAL_FLYWEIGHT_RADIUS,
    ):
        super().__init__(x_start, x_end)
        self.r_initial = r_initial
        self.end_length = end_length
        self.C = ((2 * r_initial) + prev_seg_height) ** 2 - x_start**2
        self.x_offset = math.sqrt((initial_slope**2 * self.C) / (1 - initial_slope**2))
        # print(f"X offset: {self.x_offset}, F(x_offset): {self.f(self.x_offset)}, F'(x_offset): {self.f_prime(self.x_offset)}")
        # Do the same but pass in x_start + x_offset
        # print(f"X start: {self.x_start}, F(x_start + x_offset): {self.f(self.x_start + self.x_offset)}, F'(x_start + x_offset): {self.f_prime(self.x_start + self.x_offset)}")

    def x_shift(self, x: float) -> float:
        return (x - self.x_start) - self.x_offset

    def f(self, x: float) -> float:
        return math.sqrt(x**2 + self.C) - self.r_initial

    def f_prime(self, x: float) -> float:
        return x / math.sqrt(x**2 + self.C)

    def height(self, x: float) -> float:
        adjusted_x = self.x_shift(x)
        starting_height = self.f(-self.x_offset)
        return self.f(adjusted_x) - starting_height + self.y_start

    def slope(self, x: float) -> float:
        adjusted_x = self.x_shift(x)
        return self.f_prime(adjusted_x)
