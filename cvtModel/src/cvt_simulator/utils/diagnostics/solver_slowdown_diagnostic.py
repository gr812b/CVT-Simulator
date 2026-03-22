"""Diagnostic script for investigating slow CVT simulation segments.

Runs the phase-1 ODE solve directly and reports:
- solver workload (nfev, steps, min/median internal dt)
- where tiny time steps occur
- relationship to near shift-force balance (|net axial| small)
- cProfile hotspots by cumulative time
"""

from __future__ import annotations

import cProfile
import io
import pstats
import time

import numpy as np
from cvt_simulator.models.model_initializer import get_models
from cvt_simulator.models.ramps.ramp_config import (
    CircularSegmentConfig,
    LinearSegmentConfig,
    PiecewiseRampConfig,
)
from cvt_simulator.simulation_runner import SimulationRunner
from cvt_simulator.utils.simulation_args import SimulationArgs
from cvt_simulator.utils.simulation_constraints import (
    # kept for compatibility if low-level solve path is reintroduced
    car_velocity_constraint_event,
    get_shift_steady_event,
    get_mid_shift_steady_event,
    get_mid_shift_wake_event,
    shift_constraint_event,
)
from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.constants.car_specs import MAX_SHIFT


MAX_WALL_TIME_SECONDS = 280
ENABLE_PROFILING = False


def _shift_at_time(
    time_arr: np.ndarray, shift_arr: np.ndarray, t_query: float
) -> float:
    idx = int(np.searchsorted(time_arr, t_query, side="left"))
    idx = min(max(idx, 0), len(time_arr) - 1)
    return float(shift_arr[idx])


def _estimate_first_quasi_steady_time(
    time_arr: np.ndarray,
    shift_arr: np.ndarray,
    window_s: float = 0.5,
    shift_span_tol: float = 5e-5,
    vel_tol: float = 5e-4,
) -> float | None:
    if len(time_arr) < 3:
        return None

    dt = np.diff(time_arr)
    if not np.all(dt > 0):
        return None

    vel = np.diff(shift_arr) / dt
    for i in range(len(time_arr) - 1):
        t0 = float(time_arr[i])
        j = int(np.searchsorted(time_arr, t0 + window_s, side="right")) - 1
        if j <= i + 1:
            continue
        span = float(np.max(shift_arr[i : j + 1]) - np.min(shift_arr[i : j + 1]))
        vmax = float(np.max(np.abs(vel[i:j])))
        if span <= shift_span_tol and vmax <= vel_tol:
            return t0
    return None


def build_user_case_args() -> SimulationArgs:
    """Build the exact user-reported custom case for diagnostics."""
    primary_ramp = PiecewiseRampConfig(
        segments=[
            CircularSegmentConfig(
                length=0.002,
                angle_start=75.0,
                angle_end=50.0,
                quadrant=2,
            ),
            CircularSegmentConfig(
                length=0.022,
                angle_start=50.0,
                angle_end=20.0,
                quadrant=2,
            ),
        ]
    )

    secondary_ramp = PiecewiseRampConfig(
        segments=[
            LinearSegmentConfig(
                length=1.0,
                angle=50.0,
            )
        ]
    )

    return SimulationArgs(
        flyweight_mass=0.5,
        primary_spring_rate=12784.0,
        primary_spring_pretension=0.1,
        primary_ramp_config=primary_ramp,
        secondary_torsion_spring_rate=3.476,
        secondary_compression_spring_rate=7000.0,
        secondary_rotational_spring_pretension=800.0,
        secondary_linear_spring_pretension=0.1,
        secondary_ramp_config=secondary_ramp,
        vehicle_weight=225.0,
        driver_weight=75.0,
        traction=100.0,
        angle_of_incline=0.0,
        total_distance=200.0,
    )


def run_single_case(
    case_name: str, args: SimulationArgs, enable_profiling: bool
) -> dict:
    print(f"\n=== Input Case: {case_name} ===")
    print(args)
    system_model = get_models(args)
    progress_state = {
        "start_wall": time.perf_counter(),
        "last_wall": 0.0,
        "last_percent": -1.0,
    }
    transitions: list[dict] = []

    total_time_hint = float(SimulationRunner.TOTAL_SIM_TIME)

    def progress_callback(
        progress_percent: float,
        sim_time_s: float | None = None,
        shift_distance: float | None = None,
    ):
        now = time.perf_counter()
        elapsed = now - progress_state["start_wall"]
        if elapsed >= MAX_WALL_TIME_SECONDS:
            raise TimeoutError(
                f"Diagnostic exceeded {MAX_WALL_TIME_SECONDS:.0f}s wall time at "
                f"~{progress_percent:.2f}% progress."
            )

        if (
            now - progress_state["last_wall"] >= 1.0
            and progress_percent - progress_state["last_percent"] >= 0.2
        ):
            t_est = (
                float(sim_time_s)
                if sim_time_s is not None
                else total_time_hint * (progress_percent / 100.0)
            )
            shift_str = (
                "None" if shift_distance is None else f"{float(shift_distance):.9f}"
            )
            print(
                f"[progress:{case_name}] t~{t_est:8.4f}s ({progress_percent:6.2f}%)  shift_d={shift_str}  elapsed={elapsed:7.2f}s",
                flush=True,
            )
            progress_state["last_wall"] = now
            progress_state["last_percent"] = progress_percent

    def transition_callback(payload: dict):
        transitions.append(payload)
        print(
            "[transition:{case}] {frm} -> {to} at t={t:.6f}s "
            "(reason={reason}, shift_d={d:.9f}, shift_v={v:.9f})".format(
                case=case_name,
                frm=payload["from_mode"],
                to=payload["to_mode"],
                t=payload["time"],
                reason=payload["reason"],
                d=payload["shift_distance"],
                v=payload["shift_velocity"],
            ),
            flush=True,
        )

    runner = SimulationRunner(
        system_model,
        progress_callback=progress_callback,
        transition_callback=transition_callback,
    )

    profiler = cProfile.Profile() if enable_profiling else None
    t0 = time.perf_counter()
    result = None
    timed_out = False
    timeout_message = ""
    if profiler is not None:
        profiler.enable()
    try:
        result = runner.run_simulation()
    except TimeoutError as exc:
        timed_out = True
        timeout_message = str(exc)
    finally:
        if profiler is not None:
            profiler.disable()
    elapsed = time.perf_counter() - t0

    if timed_out or result is None:
        summary = {
            "case_name": case_name,
            "status": "timeout",
            "elapsed_s": float(elapsed),
            "message": timeout_message,
            "nfev_observed": None,
            "steps": 0,
            "dt_min": None,
            "dt_median": None,
            "t_end": None,
            "shift_distance": None,
            "shift_velocity": None,
            "net_axial": None,
            "shift_accel": None,
            "mid_shift_region": None,
            "transition_count": len(transitions),
        }

        print("=== Solver Summary ===")
        print(f"elapsed_s: {summary['elapsed_s']:.3f}")
        print(f"status: {summary['status']}")
        print(f"message: {summary['message']}")
        print(f"transition_count: {summary['transition_count']}")

        if profiler is not None:
            print("\n=== Top cProfile (cumtime, partial run) ===")
            s = io.StringIO()
            pstats.Stats(profiler, stream=s).sort_stats("cumtime").print_stats(25)
            print(s.getvalue())
        return summary

    dt = np.diff(result.time)
    print("=== Solver Summary ===")
    print(f"elapsed_s: {elapsed:.3f}")
    print("status: completed")
    print("message: simulation_runner completed")
    print(f"steps: {len(result.time)}")
    print(f"transition_count: {len(transitions)}")
    if dt.size:
        print(f"dt_min: {float(dt.min()):.3e}")
        print(f"dt_median: {float(np.median(dt)):.3e}")
        print(f"dt<1e-6 count: {int((dt < 1e-6).sum())}")
        print(f"dt<1e-5 count: {int((dt < 1e-5).sum())}")

    # Evaluate shift model dynamics along returned mesh.
    net_axial = []
    shift_accel = []
    shift_velocity = []
    shift_distance = []
    for state in result.states:
        breakdown = system_model.get_breakdown(state)
        net_axial.append(breakdown.cvt_dynamics.net)
        shift_accel.append(breakdown.cvt_dynamics.acceleration)
        shift_velocity.append(state.shift_velocity)
        shift_distance.append(state.shift_distance)

    net_axial_arr = np.asarray(net_axial)
    shift_accel_arr = np.asarray(shift_accel)
    shift_velocity_arr = np.asarray(shift_velocity)
    shift_distance_arr = np.asarray(shift_distance)

    print("\n=== Dynamics Summary ===")
    print(f"|net_axial| median [N]: {float(np.median(np.abs(net_axial_arr))):.6f}")
    print(
        f"|shift_accel| median [m/s^2]: {float(np.median(np.abs(shift_accel_arr))):.6f}"
    )
    print(
        f"|shift_velocity| median [m/s]: {float(np.median(np.abs(shift_velocity_arr))):.6f}"
    )
    print("\n=== Shift Distance Probes ===")
    for tq in (1.0, 2.0, 2.5, 3.0, 3.5, 4.0):
        if tq <= float(result.time[-1]):
            print(
                f"shift_distance(t={tq:.1f}s): {_shift_at_time(result.time, shift_distance_arr, tq):.9f}"
            )

    first_quasi_steady = _estimate_first_quasi_steady_time(
        result.time, shift_distance_arr
    )
    if first_quasi_steady is None:
        print("first_quasi_steady_time: None")
    else:
        print(f"first_quasi_steady_time: {first_quasi_steady:.6f}s")

    near_balance = np.abs(net_axial_arr) < 1.0
    print(
        f"near_balance_points (|net|<1N): {int(near_balance.sum())}/{len(near_balance)}"
    )

    if dt.size and near_balance.size > 1:
        interval_mask = near_balance[:-1]
        if interval_mask.any():
            dt_bal = dt[interval_mask]
            print(f"near_balance dt_min: {float(dt_bal.min()):.3e}")
            print(f"near_balance dt_median: {float(np.median(dt_bal)):.3e}")

    # Print the tightest-step region and corresponding state context.
    if dt.size:
        k = int(np.argmin(dt))
        print("\n=== Tightest Step Context ===")
        print(f"t[k]: {float(result.time[k]):.9f}")
        print(f"dt_min: {float(dt[k]):.3e}")
        print(f"shift_distance[k]: {float(shift_distance_arr[k]):.9f}")
        print(f"shift_velocity[k]: {float(shift_velocity_arr[k]):.9f}")
        print(f"net_axial[k] [N]: {float(net_axial_arr[k]):.9f}")
        print(f"shift_accel[k] [m/s^2]: {float(shift_accel_arr[k]):.9f}")

    if transitions:
        print("\n=== Transition Log ===")
        for i, tr in enumerate(transitions, start=1):
            print(
                f"{i}. {tr['from_mode']} -> {tr['to_mode']} at t={tr['time']:.6f}s "
                f"reason={tr['reason']} shift_d={tr['shift_distance']:.9f}"
            )

        transition_times = np.asarray(
            [float(tr["time"]) for tr in transitions], dtype=float
        )
        if transition_times.size > 1:
            transition_dt = np.diff(transition_times)
            print("\n=== Transition Cadence ===")
            print(f"min interval [s]: {float(np.min(transition_dt)):.6e}")
            print(f"median interval [s]: {float(np.median(transition_dt)):.6e}")
            print(f"intervals < 1e-2s: {int(np.sum(transition_dt < 1e-2))}")
            print(f"intervals < 1e-3s: {int(np.sum(transition_dt < 1e-3))}")

        mid_shift_steady_event = get_mid_shift_steady_event(system_model)
        mid_shift_wake_event = get_mid_shift_wake_event(system_model)

        print("\n=== Transition Threshold Probes ===")
        for i, tr in enumerate(transitions, start=1):
            t_tr = float(tr["time"])
            idx = int(np.searchsorted(result.time, t_tr, side="left"))
            idx = min(max(idx, 0), len(result.states) - 1)
            state = result.states[idx]
            y = np.asarray(state.to_array(), dtype=float)
            steady_val = float(mid_shift_steady_event(t_tr, y.copy()))
            wake_val = float(mid_shift_wake_event(t_tr, y.copy()))
            print(
                f"{i}. t={t_tr:.6f}s reason={tr['reason']} "
                f"steady_event={steady_val:+.6e} wake_event={wake_val:+.6e}"
            )

    if profiler is not None:
        print("\n=== Top cProfile (cumtime) ===")
        s = io.StringIO()
        pstats.Stats(profiler, stream=s).sort_stats("cumtime").print_stats(25)
        print(s.getvalue())

    summary = {
        "case_name": case_name,
        "status": "completed",
        "elapsed_s": float(elapsed),
        "message": "simulation_runner completed",
        "nfev_observed": None,
        "steps": int(len(result.time)),
        "dt_min": float(dt.min()) if dt.size else None,
        "dt_median": float(np.median(dt)) if dt.size else None,
        "t_end": float(result.time[-1]),
        "shift_distance": (
            float(shift_distance_arr[-1]) if shift_distance_arr.size else None
        ),
        "shift_velocity": (
            float(shift_velocity_arr[-1]) if shift_velocity_arr.size else None
        ),
        "net_axial": float(net_axial_arr[-1]) if net_axial_arr.size else None,
        "shift_accel": float(shift_accel_arr[-1]) if shift_accel_arr.size else None,
        "transition_count": len(transitions),
        "mid_shift_region": (
            bool(
                (shift_distance_arr[-1] > 1e-6)
                and (shift_distance_arr[-1] < float(MAX_SHIFT) - 1e-6)
            )
            if shift_distance_arr.size
            else None
        ),
    }
    return summary


def run_diagnostic() -> None:
    summary = run_single_case("user_case", build_user_case_args(), ENABLE_PROFILING)
    print("\n=== Final Summary ===")
    print(f"status: {summary['status']}")
    print(f"elapsed_s: {summary['elapsed_s']:.3f}")
    print(f"steps: {summary['steps']}")
    print(f"transition_count: {summary['transition_count']}")
    print(f"t_end: {summary['t_end']}")


if __name__ == "__main__":
    run_diagnostic()
