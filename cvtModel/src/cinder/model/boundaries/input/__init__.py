"""Input-shaft boundaries such as engines, motors, or dynos."""

from .engine import *

from typing import Protocol

class InputTorqueBoundary(Protocol):
    def evaluate(self, angular_speed: float) -> float: ...

__all__ = [name for name in globals() if not name.startswith("_")]
