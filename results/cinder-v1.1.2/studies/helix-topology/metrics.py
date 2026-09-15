"""Pure post-processing metrics for the helix contact-topology exploration.

This module intentionally has no CINDER imports so the sign/integration logic
can be unit-tested independently of the simulation environment.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable


@dataclass(frozen=True)
class NegativePartIntegral:
    duration_s: float
    impulse: float
    first_entry_time_s: float | None
    crossing_count: int


def _finite(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if isfinite(x) else None


def deduplicate_by_time(
    rows: Iterable[dict[str, Any]],
    *,
    time_key: str = "time_s",
) -> list[dict[str, Any]]:
    """Keep the last sample at each exact time and return rows in time order.

    Hybrid traces can contain the pre-event segment endpoint and the post-event
    successor-segment start at the same physical time.  The zero-measure pre-
    event duplicate should not be counted twice in duration/impulse metrics, so
    the later row wins.
    """

    by_time: dict[float, dict[str, Any]] = {}
    for row in rows:
        t = _finite(row.get(time_key))
        if t is None:
            continue
        by_time[t] = row
    return [by_time[t] for t in sorted(by_time)]


def _crossing_fraction(y0: float, y1: float) -> float:
    """Fraction of the line segment from y0 to y1 at which y=0."""
    denom = y1 - y0
    if denom == 0.0:
        return 0.5
    value = -y0 / denom
    return min(1.0, max(0.0, value))


def integrate_negative_part(
    times: Iterable[float],
    values: Iterable[float],
) -> NegativePartIntegral:
    """Exact piecewise-linear duration and area of the negative part.

    ``impulse`` is ``integral(max(-y, 0) dt)``.  Zero crossings are linearly
    interpolated instead of being quantized to the sample interval.
    """

    t = [float(x) for x in times]
    y = [float(x) for x in values]
    if len(t) != len(y):
        raise ValueError("times and values must have the same length")
    if len(t) < 2:
        return NegativePartIntegral(0.0, 0.0, None, 0)
    if any(not isfinite(x) for x in (*t, *y)):
        raise ValueError("times and values must be finite")
    if any(t1 < t0 for t0, t1 in zip(t, t[1:])):
        raise ValueError("times must be nondecreasing")

    duration = 0.0
    impulse = 0.0
    first_entry: float | None = t[0] if y[0] < 0.0 else None
    crossings = 0

    for t0, t1, y0, y1 in zip(t, t[1:], y, y[1:]):
        dt = t1 - t0
        if dt <= 0.0:
            continue

        n0 = y0 < 0.0
        n1 = y1 < 0.0
        if n0 and n1:
            duration += dt
            impulse += -0.5 * (y0 + y1) * dt
            continue
        if (not n0) and (not n1):
            # A sample exactly on zero does not by itself create a crossing.
            continue

        frac = _crossing_fraction(y0, y1)
        tz = t0 + frac * dt
        crossings += 1
        if n0:
            neg_dt = frac * dt
            duration += neg_dt
            impulse += 0.5 * (-y0) * neg_dt
        else:
            neg_dt = (1.0 - frac) * dt
            duration += neg_dt
            impulse += 0.5 * (-y1) * neg_dt
            if first_entry is None:
                first_entry = tz

    return NegativePartIntegral(duration, impulse, first_entry, crossings)


def integrate_abs_value_where_driver_negative(
    times: Iterable[float],
    driver: Iterable[float],
    values: Iterable[float],
) -> float:
    """Piecewise-linear integral of ``abs(values)`` where ``driver < 0``.

    The boundary fraction is set by the driver zero crossing.  The reported
    force impulse is therefore conditioned on the torque-domain contact state,
    exactly as required by the study definition.
    """

    t = [float(x) for x in times]
    d = [float(x) for x in driver]
    v = [float(x) for x in values]
    if not (len(t) == len(d) == len(v)):
        raise ValueError("times, driver, and values must have the same length")
    if len(t) < 2:
        return 0.0
    if any(not isfinite(x) for x in (*t, *d, *v)):
        raise ValueError("inputs must be finite")

    total = 0.0
    for t0, t1, d0, d1, v0, v1 in zip(t, t[1:], d, d[1:], v, v[1:]):
        dt = t1 - t0
        if dt <= 0.0:
            continue
        n0, n1 = d0 < 0.0, d1 < 0.0
        if n0 and n1:
            total += 0.5 * (abs(v0) + abs(v1)) * dt
            continue
        if (not n0) and (not n1):
            continue

        frac = _crossing_fraction(d0, d1)
        vz = v0 + frac * (v1 - v0)
        if n0:
            neg_dt = frac * dt
            total += 0.5 * (abs(v0) + abs(vz)) * neg_dt
        else:
            neg_dt = (1.0 - frac) * dt
            total += 0.5 * (abs(vz) + abs(v1)) * neg_dt
    return total


def contact_topology_metrics(
    rows: Iterable[dict[str, Any]],
    *,
    case_start_s: float,
    case_end_s: float,
    margin_key: str = "helix_reacted_torque_margin_Nm",
    force_key: str = "helix_full_reaction_force_N",
) -> dict[str, Any]:
    """Summarize opposite-flank demand from an augmented simulation trace.

    Finite-margin samples are integrated in contiguous runs.  A deadzone or
    other interval with no resolved engaged helix margin is therefore never
    silently bridged by the duration/impulse calculation.
    """

    if not (isfinite(case_start_s) and isfinite(case_end_s)):
        raise ValueError("case bounds must be finite")
    if case_end_s < case_start_s:
        raise ValueError("case_end_s must not precede case_start_s")

    unique = deduplicate_by_time(rows)
    runs: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    finite_count = 0
    all_margins: list[float] = []

    for row in unique:
        m = _finite(row.get(margin_key))
        f = _finite(row.get(force_key))
        t = _finite(row.get("time_s"))
        if t is None or m is None or f is None:
            if current:
                runs.append(current)
                current = []
            continue
        item = {**row, "__t": t, "__m": m, "__f": f}
        current.append(item)
        finite_count += 1
        all_margins.append(m)
    if current:
        runs.append(current)

    if not runs:
        return {
            "resolved_margin_sample_count": 0,
            "resolved_margin_span_s": 0.0,
            "opposite_flank_duration_s": 0.0,
            "D_opp_case": 0.0,
            "D_opp_engaged": 0.0,
            "I_opp_tau_Nm_s": 0.0,
            "I_opp_force_N_s": 0.0,
            "minimum_margin_Nm": None,
            "maximum_margin_Nm": None,
            "minimum_absolute_margin_Nm": None,
            "zero_crossing_count": 0,
            "first_opposite_flank_time_s": None,
        }

    resolved_duration = 0.0
    negative_duration = 0.0
    torque_impulse = 0.0
    force_impulse = 0.0
    crossings = 0
    first_entry: float | None = None

    for run in runs:
        times = [r["__t"] for r in run]
        margins = [r["__m"] for r in run]
        forces = [r["__f"] for r in run]
        if len(times) >= 2:
            resolved_duration += max(0.0, times[-1] - times[0])
        neg = integrate_negative_part(times, margins)
        negative_duration += neg.duration_s
        torque_impulse += neg.impulse
        force_impulse += integrate_abs_value_where_driver_negative(
            times, margins, forces
        )
        crossings += neg.crossing_count
        if neg.first_entry_time_s is not None:
            if first_entry is None or neg.first_entry_time_s < first_entry:
                first_entry = neg.first_entry_time_s

    case_duration = max(0.0, case_end_s - case_start_s)
    return {
        "resolved_margin_sample_count": finite_count,
        "resolved_margin_span_s": resolved_duration,
        "opposite_flank_duration_s": negative_duration,
        "D_opp_case": negative_duration / case_duration if case_duration > 0.0 else 0.0,
        "D_opp_engaged": (
            negative_duration / resolved_duration if resolved_duration > 0.0 else 0.0
        ),
        "I_opp_tau_Nm_s": torque_impulse,
        "I_opp_force_N_s": force_impulse,
        "minimum_margin_Nm": min(all_margins),
        "maximum_margin_Nm": max(all_margins),
        "minimum_absolute_margin_Nm": min(abs(x) for x in all_margins),
        "zero_crossing_count": crossings,
        "first_opposite_flank_time_s": first_entry,
    }
