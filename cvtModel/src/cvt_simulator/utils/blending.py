class SignalBlendController:
    """Agnostic scalar blend controller driven by signal magnitude.

    The controller outputs a blend weight in [0, 1] using a deadzone and a
    short transition band:
    - |signal| <= deadzone: weight = 0
    - |signal| >= deadzone + transition_width: weight = 1
    - otherwise: smoothstep transition in between
    """

    def __init__(
        self,
        deadzone: float,
        transition_width: float,
        hard_threshold: bool = False,
    ):
        self.deadzone = max(0.0, float(deadzone))
        self.transition_width = max(0.0, float(transition_width))
        self.hard_threshold = bool(hard_threshold)

    def weight(self, signal: float) -> float:
        magnitude = abs(float(signal))

        if self.hard_threshold:
            return 1.0 if magnitude > self.deadzone else 0.0

        if magnitude <= self.deadzone:
            return 0.0
        if self.transition_width <= 0.0:
            return 1.0
        if magnitude >= self.deadzone + self.transition_width:
            return 1.0

        x = (magnitude - self.deadzone) / self.transition_width
        return x * x * (3.0 - 2.0 * x)

    def blend(self, low_value: float, high_value: float, signal: float) -> float:
        w = self.weight(signal)
        return (1.0 - w) * low_value + w * high_value
