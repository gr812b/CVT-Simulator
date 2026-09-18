"""Deterministic smart design for the Baja reduced-belt operating envelope.

The design is not a tuning optimization and not a Cartesian grid.  It uses a
low-discrepancy Halton sequence over physically interpretable disturbance axes,
then adds a small set of edge anchors and documented preload robustness cases.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, log, radians
from typing import Iterable


@dataclass(frozen=True, slots=True)
class EnvelopeCase:
    name: str
    title: str
    start_time_s: float
    rise_time_s: float
    target_grade_deg: float
    source: str
    tune_variant: str = "reference"

    def as_protocol(self) -> dict[str, object]:
        return {
            "name": self.name,
            "title": self.title,
            "family": "baja_envelope",
            "purpose": (
                "Mechanistic Baja-envelope sample over disturbance timing, signed road grade, "
                "and load-rise timescale. No CVT governing equation is modified."
            ),
            "design_source": self.source,
            "tune_variant": self.tune_variant,
            "controlled_load": {
                "kind": "smooth_time_programmed_grade",
                "start_time_s": self.start_time_s,
                "rise_time_s": self.rise_time_s,
                "target_grade_deg": self.target_grade_deg,
            },
        }


def van_der_corput(index: int, base: int) -> float:
    if index < 1 or base < 2:
        raise ValueError("index must be >=1 and base >=2")
    value = 0.0
    denominator = 1.0
    n = int(index)
    while n:
        n, remainder = divmod(n, base)
        denominator *= base
        value += remainder / denominator
    return value


def halton_point(index: int) -> tuple[float, float, float]:
    return (
        van_der_corput(index, 2),
        van_der_corput(index, 3),
        van_der_corput(index, 5),
    )


def _grade_from_unit(value: float) -> float:
    """Map [0,1) into nontrivial downhill/uphill Baja grade demand.

    Forty percent of the design is downhill/unloading (-5 to -20 deg), sixty
    percent uphill/loading (+5 to +30 deg).  Near-zero disturbances are left to
    the baseline cases rather than wasting envelope samples.
    """
    u = float(value)
    if u < 0.4:
        return -(5.0 + 15.0 * (u / 0.4))
    return 5.0 + 25.0 * ((u - 0.4) / 0.6)


def _log_map(value: float, lower: float, upper: float) -> float:
    return exp(log(lower) + float(value) * log(upper / lower))


def build_baja_envelope(space_filling_count: int = 18) -> tuple[EnvelopeCase, ...]:
    if space_filling_count < 0:
        raise ValueError("space_filling_count must be non-negative")
    cases: list[EnvelopeCase] = []
    for index in range(1, space_filling_count + 1):
        u_start, u_grade, u_rise = halton_point(index)
        start = 1.05 + u_start * (3.35 - 1.05)
        grade = _grade_from_unit(u_grade)
        rise = _log_map(u_rise, 0.05, 0.80)
        cases.append(
            EnvelopeCase(
                name=f"envelope_{index:02d}",
                title=f"Envelope {index:02d}: {grade:+.1f} deg over {1000.0*rise:.0f} ms",
                start_time_s=start,
                rise_time_s=rise,
                target_grade_deg=grade,
                source="halton_space_filling",
            )
        )

    # Edge anchors deliberately expose sign, ratio/timing, and response timescale.
    anchors = (
        ("anchor_early_uphill_fast", "Early +30 deg / 50 ms", 1.05, 0.05, +30.0),
        ("anchor_early_downhill_fast", "Early -20 deg / 50 ms", 1.05, 0.05, -20.0),
        ("anchor_mid_uphill_medium", "Mid +30 deg / 200 ms", 1.80, 0.20, +30.0),
        ("anchor_mid_downhill_medium", "Mid -20 deg / 200 ms", 1.80, 0.20, -20.0),
        ("anchor_late_uphill_slow", "Late +30 deg / 800 ms", 2.80, 0.80, +30.0),
        ("anchor_late_downhill_slow", "Late -20 deg / 800 ms", 2.80, 0.80, -20.0),
    )
    for name, title, start, rise, grade in anchors:
        cases.append(
            EnvelopeCase(
                name=name,
                title=title,
                start_time_s=start,
                rise_time_s=rise,
                target_grade_deg=grade,
                source="mechanistic_anchor",
            )
        )

    # These preload values are the documented coordinate-search bounds used by
    # the repository's fixed-pivot tuning helper.  They are not asserted to be
    # exact clamp-force multipliers; the resulting normal force/utilization is
    # measured by the study.
    for tune_key, tune_label in (
        ("lower_secondary_preload", "lower secondary preload"),
        ("higher_secondary_preload", "higher secondary preload"),
    ):
        for grade in (+30.0, -20.0):
            sign = "uphill" if grade > 0 else "downhill"
            cases.append(
                EnvelopeCase(
                    name=f"robust_{tune_key}_{sign}",
                    title=f"{tune_label}, {grade:+.0f} deg / 200 ms",
                    start_time_s=1.80,
                    rise_time_s=0.20,
                    target_grade_deg=grade,
                    source="tune_robustness_anchor",
                    tune_variant=tune_key,
                )
            )
    return tuple(cases)


def apply_tune_variant(document: dict, variant: str) -> None:
    """Apply one documented secondary-preload robustness variant in-place."""
    if variant == "reference":
        return
    settings = {
        "lower_secondary_preload": (0.105, radians(280.0)),
        "higher_secondary_preload": (0.115, radians(320.0)),
    }
    try:
        compression, twist = settings[variant]
    except KeyError as exc:
        raise ValueError(f"Unknown tune variant: {variant}") from exc

    found_spring = False
    found_helix = False
    components = document["assembly"]["pulleys"]["secondary"]["components"]
    for component in components:
        kind = component.get("kind")
        if kind == "axial_spring":
            component["initial_compression_m"] = compression
            found_spring = True
        elif kind == "helical_torque_reaction":
            component["initial_twist_rad"] = twist
            found_helix = True
    if not (found_spring and found_helix):
        raise RuntimeError(
            "Tune-robustness variant expected secondary axial_spring and helical_torque_reaction components."
        )
