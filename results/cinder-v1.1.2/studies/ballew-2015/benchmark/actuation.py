"""Study-local prescribed axial-force laws for the Ballew benchmark."""

from __future__ import annotations

import csv
from bisect import bisect_right
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

from cinder.model.cvt.actuation import PulleyActuationContext
from cinder.model.cvt.closure import AffineClosureScalar


@dataclass(frozen=True, slots=True)
class ConstantAxialForce:
    force_n: float

    def __post_init__(self) -> None:
        if not isfinite(self.force_n):
            raise ValueError("force_n must be finite.")

    def evaluate(self, context: PulleyActuationContext) -> AffineClosureScalar:
        del context
        return AffineClosureScalar(bias=self.force_n)


@dataclass(frozen=True, slots=True)
class TabulatedAxialForce:
    times_s: tuple[float, ...]
    forces_n: tuple[float, ...]

    def __post_init__(self) -> None:
        times = tuple(float(value) for value in self.times_s)
        forces = tuple(float(value) for value in self.forces_n)
        if len(times) < 2 or len(times) != len(forces):
            raise ValueError("TabulatedAxialForce requires aligned vectors with >=2 samples.")
        if not all(isfinite(value) for value in (*times, *forces)):
            raise ValueError("tabulated force samples must all be finite.")
        if any(right <= left for left, right in zip(times, times[1:])):
            raise ValueError("times_s must be strictly increasing.")
        object.__setattr__(self, "times_s", times)
        object.__setattr__(self, "forces_n", forces)

    @classmethod
    def from_csv(cls, path: str | Path) -> "TabulatedAxialForce":
        times: list[float] = []
        forces: list[float] = []
        with Path(path).open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            required = {"time_s", "primary_axial_force_n"}
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise ValueError(
                    "force CSV must contain time_s and primary_axial_force_n columns."
                )
            for row in reader:
                times.append(float(row["time_s"]))
                forces.append(float(row["primary_axial_force_n"]))
        return cls(tuple(times), tuple(forces))

    def evaluate(self, context: PulleyActuationContext) -> AffineClosureScalar:
        time = float(context.time)
        if time < self.times_s[0] or time > self.times_s[-1]:
            raise ValueError(
                f"tabulated force does not cover t={time:.12g} s; available interval is "
                f"[{self.times_s[0]:.12g}, {self.times_s[-1]:.12g}] s."
            )
        if time == self.times_s[-1]:
            force = self.forces_n[-1]
        else:
            upper = bisect_right(self.times_s, time)
            lower = upper - 1
            t0, t1 = self.times_s[lower], self.times_s[upper]
            f0, f1 = self.forces_n[lower], self.forces_n[upper]
            fraction = (time - t0) / (t1 - t0)
            force = f0 + fraction * (f1 - f0)
        return AffineClosureScalar(bias=force)
