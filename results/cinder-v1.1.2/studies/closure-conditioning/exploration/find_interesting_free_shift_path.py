"""Find and lock an interesting admissible FREE/STICK_STICK path cheaply.

This utility does *not* build any lambda-plane maps.  It searches only the instantaneous
production closure at candidate fixed-boundary torque pairs, then writes a locked CSV
that `exploration/animate_controlled_free_shift_path.py --path-csv ...` can consume later.

The default objective deliberately asks the actual stick-stick utilization to rise from
about 0.12 to about 0.45 and then fall again, while penalizing abrupt torque/lambda jumps.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import run as cc_run
from animate_controlled_free_shift_path import (
    classify_candidate,
    frame_recipe,
    load_base,
)

HERE = Path(__file__).resolve().parents[1]
ARTIFACTS = HERE / "artifacts" / "controlled-free-shift-path-search"

_WORKER_DECODED = None
_WORKER_LIBRARY = None
_WORKER_ARGS = None


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--frames", type=int, default=120,
                   help="Final locked-path frame count used by the later GIF run.")
    p.add_argument("--anchors", type=int, default=31,
                   help="Number of frames used for the broad global torque search.")
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument("--shift-start", type=float, default=0.30)
    p.add_argument("--shift-end", type=float, default=0.70)
    p.add_argument("--shift-speed-mm-s", type=float, default=20.0)
    p.add_argument("--belt-speed-start", type=float, default=12.0)
    p.add_argument("--belt-speed-end", type=float, default=16.0)
    p.add_argument("--primary-rpm-start", type=float, default=None)
    p.add_argument("--primary-rpm-end", type=float, default=None)

    p.add_argument("--torque-limit", type=float, default=40.0,
                   help="Search fixed-boundary torques from -limit to +limit [Nm].")
    p.add_argument("--torque-step", type=float, default=5.0,
                   help="Broad anchor-search torque-grid spacing [Nm].")
    p.add_argument("--refine-radius", type=float, default=10.0,
                   help="Per-final-frame local torque refinement radius [Nm].")
    p.add_argument("--refine-step", type=float, default=2.5,
                   help="Per-final-frame local torque refinement spacing [Nm].")

    p.add_argument("--target-util-start", type=float, default=0.12,
                   help="Target max(|lambda_p|,|lambda_s|) at the start.")
    p.add_argument("--target-util-peak", type=float, default=0.45,
                   help="Target max(|lambda_p|,|lambda_s|) near the turnaround.")
    p.add_argument("--target-util-end", type=float, default=0.12,
                   help="Target max(|lambda_p|,|lambda_s|) at the end.")
    p.add_argument("--util-weight", type=float, default=10.0)
    p.add_argument("--torque-continuity-weight", type=float, default=0.015)
    p.add_argument("--lambda-continuity-weight", type=float, default=2.0)
    p.add_argument("--candidate-keep", type=int, default=80,
                   help="Maximum admissible candidates retained at each anchor for dynamic programming.")
    p.add_argument("--output", type=Path, default=ARTIFACTS / "locked_path.csv")
    p.add_argument("--no-open", action="store_true")
    return p.parse_args()


def kinematic_args(args):
    return SimpleNamespace(
        shift_start=float(args.shift_start),
        shift_end=float(args.shift_end),
        shift_speed_mm_s=float(args.shift_speed_mm_s),
        belt_speed_start=float(args.belt_speed_start),
        belt_speed_end=float(args.belt_speed_end),
        primary_rpm_start=args.primary_rpm_start,
        primary_rpm_end=args.primary_rpm_end,
    )


def target_util_for_frame(frame_no: int, frames: int, args) -> float:
    if frames <= 1:
        return float(args.target_util_start)
    x = frame_no / (frames - 1)
    # Smooth triangular target: start -> peak at midpoint -> end.
    if x <= 0.5:
        u = x / 0.5
        return (1.0 - u) * float(args.target_util_start) + u * float(args.target_util_peak)
    u = (x - 0.5) / 0.5
    return (1.0 - u) * float(args.target_util_peak) + u * float(args.target_util_end)


def torque_values(limit: float, step: float) -> np.ndarray:
    limit = abs(float(limit))
    step = abs(float(step))
    if step <= 0.0:
        raise ValueError("torque step must be positive")
    values = np.arange(-limit, limit + 0.5 * step, step, dtype=float)
    if not np.any(np.isclose(values, 0.0)):
        values = np.sort(np.append(values, 0.0))
    return values


def worker_init(args_dict):
    global _WORKER_DECODED, _WORKER_LIBRARY, _WORKER_ARGS
    _WORKER_DECODED, _WORKER_LIBRARY = load_base()
    _WORKER_ARGS = SimpleNamespace(**args_dict)


def evaluate_candidate(recipe: dict, tp: float, ts: float, target: float):
    result, diag = classify_candidate(_WORKER_DECODED, _WORKER_LIBRARY, recipe, float(tp), float(ts))
    if result is None:
        return None
    system, cvt, _state, _mode = result
    lp = float(diag["lambda_p"])
    ls = float(diag["lambda_s"])
    util = max(abs(lp), abs(ls))
    return {
        **recipe,
        "target_util": float(target),
        "primary_torque_Nm": float(tp),
        "secondary_torque_Nm": float(ts),
        "resolved_belt_speed_m_s": float(cvt.belt_speed),
        "resolved_primary_rpm": float(cvt.primary_angular_speed * 60.0 / (2.0 * math.pi)),
        "resolved_secondary_rpm": float(cvt.secondary_angular_speed * 60.0 / (2.0 * math.pi)),
        "preflight_lambda_p": lp,
        "preflight_lambda_s": ls,
        "utilization_maxabs": util,
        "preflight_scaled_condition_A": float(diag.get("scaled_condition_A", float("nan"))),
        "primary_static_margin": float(diag.get("primary_static_margin", float("nan"))),
        "secondary_static_margin": float(diag.get("secondary_static_margin", float("nan"))),
    }


def search_anchor_worker(payload):
    frame_no, frames, recipe, target, torque_list, keep, util_weight = payload
    candidates = []
    for tp in torque_list:
        for ts in torque_list:
            c = evaluate_candidate(recipe, tp, ts, target)
            if c is not None:
                local = util_weight * (c["utilization_maxabs"] - target) ** 2
                # tiny load penalty breaks ties in favor of less heroic boundary loads
                local += 1.0e-4 * (abs(tp) + abs(ts))
                c["local_cost"] = float(local)
                candidates.append(c)
    candidates.sort(key=lambda c: c["local_cost"])
    return frame_no, candidates[:keep], len(candidates)


def transition_cost(prev: dict, cur: dict, args) -> float:
    dt = abs(cur["primary_torque_Nm"] - prev["primary_torque_Nm"]) + abs(cur["secondary_torque_Nm"] - prev["secondary_torque_Nm"])
    dl = math.hypot(
        cur["preflight_lambda_p"] - prev["preflight_lambda_p"],
        cur["preflight_lambda_s"] - prev["preflight_lambda_s"],
    )
    return float(args.torque_continuity_weight) * dt + float(args.lambda_continuity_weight) * dl


def choose_anchor_path(candidate_sets: list[list[dict]], args) -> list[dict]:
    if not candidate_sets or any(not rows for rows in candidate_sets):
        raise RuntimeError("At least one anchor has no admissible FREE/STICK_STICK candidates.")
    costs = [np.asarray([c["local_cost"] for c in candidate_sets[0]], dtype=float)]
    parents: list[np.ndarray] = [np.full(len(candidate_sets[0]), -1, dtype=int)]
    for i in range(1, len(candidate_sets)):
        prev_rows = candidate_sets[i-1]
        cur_rows = candidate_sets[i]
        prev_cost = costs[-1]
        cur_cost = np.full(len(cur_rows), np.inf)
        cur_parent = np.full(len(cur_rows), -1, dtype=int)
        for j, cur in enumerate(cur_rows):
            best = np.inf
            best_k = -1
            for k, prev in enumerate(prev_rows):
                value = prev_cost[k] + cur["local_cost"] + transition_cost(prev, cur, args)
                if value < best:
                    best = value
                    best_k = k
            cur_cost[j] = best
            cur_parent[j] = best_k
        costs.append(cur_cost)
        parents.append(cur_parent)
    idx = int(np.argmin(costs[-1]))
    chosen = [None] * len(candidate_sets)
    for i in range(len(candidate_sets)-1, -1, -1):
        chosen[i] = candidate_sets[i][idx]
        idx = int(parents[i][idx]) if i > 0 else -1
    return chosen  # type: ignore[return-value]


def interpolate_anchor_torques(anchor_frames: np.ndarray, anchor_path: list[dict], frames: int):
    xp = anchor_frames.astype(float)
    tp = np.asarray([r["primary_torque_Nm"] for r in anchor_path], dtype=float)
    ts = np.asarray([r["secondary_torque_Nm"] for r in anchor_path], dtype=float)
    x = np.arange(frames, dtype=float)
    return np.interp(x, xp, tp), np.interp(x, xp, ts)


def refine_final_path(decoded, library, recipes: list[dict], tp_guess: np.ndarray, ts_guess: np.ndarray, args):
    # This stage is intentionally serial so continuity can use the immediately preceding
    # accepted frame.  It is still cheap: only a small local torque neighborhood is tested.
    global _WORKER_DECODED, _WORKER_LIBRARY
    _WORKER_DECODED, _WORKER_LIBRARY = decoded, library
    resolved = []
    previous = None
    offsets = np.arange(-abs(args.refine_radius), abs(args.refine_radius) + 0.5 * abs(args.refine_step), abs(args.refine_step))
    for i, recipe in enumerate(recipes):
        target = target_util_for_frame(i, len(recipes), args)
        candidates = []
        for dp in offsets:
            for ds in offsets:
                tp = float(tp_guess[i] + dp)
                ts = float(ts_guess[i] + ds)
                if abs(tp) > abs(args.torque_limit) + 1e-12 or abs(ts) > abs(args.torque_limit) + 1e-12:
                    continue
                c = evaluate_candidate(recipe, tp, ts, target)
                if c is None:
                    continue
                cost = float(args.util_weight) * (c["utilization_maxabs"] - target) ** 2
                cost += 2.5e-3 * (abs(dp) + abs(ds))
                if previous is not None:
                    cost += transition_cost(previous, c, args)
                c["path_cost"] = float(cost)
                candidates.append(c)
        if not candidates:
            raise RuntimeError(
                f"Final frame {i} has no admissible local refinement candidate around "
                f"Tp={tp_guess[i]:.2f}, Ts={ts_guess[i]:.2f}. Increase --refine-radius or --torque-limit."
            )
        chosen = min(candidates, key=lambda c: c["path_cost"])
        resolved.append(chosen)
        previous = chosen
        print(
            f"  final {i+1:03d}/{len(recipes)} {chosen['leg']:<9s} "
            f"target={target:.3f} util={chosen['utilization_maxabs']:.3f} "
            f"lambda=({chosen['preflight_lambda_p']:+.3f},{chosen['preflight_lambda_s']:+.3f}) "
            f"Tp={chosen['primary_torque_Nm']:+.1f} Ts={chosen['secondary_torque_Nm']:+.1f}"
        )
    return resolved


def write_rows(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields, seen = [], set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def plot_preview(path: Path, rows: list[dict]):
    x = np.asarray([r["frame_no"] for r in rows])
    target = np.asarray([r["target_util"] for r in rows])
    util = np.asarray([r["utilization_maxabs"] for r in rows])
    lp = np.asarray([r["preflight_lambda_p"] for r in rows])
    ls = np.asarray([r["preflight_lambda_s"] for r in rows])
    tp = np.asarray([r["primary_torque_Nm"] for r in rows])
    ts = np.asarray([r["secondary_torque_Nm"] for r in rows])
    rpm_p = np.asarray([r["resolved_primary_rpm"] for r in rows])
    rpm_s = np.asarray([r["resolved_secondary_rpm"] for r in rows])
    sf = np.asarray([r["shift_fraction"] for r in rows])

    fig, axes = plt.subplots(4, 1, figsize=(12, 12), sharex=True, constrained_layout=True)
    axes[0].plot(x, target, "--", label="target max|lambda|")
    axes[0].plot(x, util, label="actual max|lambda|")
    axes[0].plot(x, lp, label="lambda_p")
    axes[0].plot(x, ls, label="lambda_s")
    axes[0].set_ylabel("Traction utilization")
    axes[0].grid(True, alpha=0.25); axes[0].legend(ncol=4, fontsize=8)

    axes[1].plot(x, tp, label="primary torque")
    axes[1].plot(x, ts, label="secondary torque")
    axes[1].set_ylabel("Boundary torque [Nm]")
    axes[1].grid(True, alpha=0.25); axes[1].legend()

    axes[2].plot(x, rpm_p, label="primary rpm")
    axes[2].plot(x, rpm_s, label="secondary rpm")
    axes[2].set_ylabel("Speed [rpm]")
    axes[2].grid(True, alpha=0.25); axes[2].legend()

    axes[3].plot(x, sf, label="shift fraction")
    axes[3].set_ylabel("Shift fraction")
    axes[3].set_xlabel("Frame")
    axes[3].grid(True, alpha=0.25); axes[3].legend()
    fig.suptitle("Locked FREE/STICK_STICK path preview — no lambda-plane maps computed")
    fig.savefig(path, dpi=180)
    plt.close(fig)


def maybe_open(path: Path):
    try:
        if hasattr(os, "startfile"):
            os.startfile(str(path))  # type: ignore[attr-defined]
    except Exception:
        pass


def main():
    args = parse_args()
    cc_run.verify_environment()
    if args.frames < 3:
        raise ValueError("--frames must be at least 3")
    if args.anchors < 3:
        raise ValueError("--anchors must be at least 3")
    args.anchors = min(args.anchors, args.frames)
    decoded, library = load_base()
    kargs = kinematic_args(args)
    recipes = [frame_recipe(i, args.frames, kargs) for i in range(args.frames)]

    anchor_frames = np.unique(np.round(np.linspace(0, args.frames - 1, args.anchors)).astype(int))
    tvals = torque_values(args.torque_limit, args.torque_step)
    print(
        f"Broad search: {len(anchor_frames)} anchors, {len(tvals)}x{len(tvals)} torque grid "
        f"({len(anchor_frames)*len(tvals)*len(tvals):,} cheap instantaneous candidates max)."
    )
    payloads = []
    for frame_no in anchor_frames:
        recipe = recipes[int(frame_no)]
        target = target_util_for_frame(int(frame_no), args.frames, args)
        payloads.append((int(frame_no), args.frames, recipe, target, tvals.tolist(), int(args.candidate_keep), float(args.util_weight)))

    candidate_by_frame = {}
    stats = []
    argdict = {
        "frames": args.frames,
    }
    with ProcessPoolExecutor(max_workers=max(1, int(args.jobs)), initializer=worker_init, initargs=(argdict,)) as ex:
        futures = [ex.submit(search_anchor_worker, payload) for payload in payloads]
        for fut in as_completed(futures):
            frame_no, candidates, total_admissible = fut.result()
            candidate_by_frame[frame_no] = candidates
            stats.append({"frame_no": frame_no, "admissible_candidates": total_admissible, "retained_candidates": len(candidates)})
            best = candidates[0] if candidates else None
            print(
                f"  anchor {frame_no+1:03d}/{args.frames}: admissible={total_admissible:3d} "
                + (f"best util={best['utilization_maxabs']:.3f} target={best['target_util']:.3f}" if best else "NO ADMISSIBLE CANDIDATE")
            )

    candidate_sets = [candidate_by_frame[int(i)] for i in anchor_frames]
    anchor_path = choose_anchor_path(candidate_sets, args)
    tp_guess, ts_guess = interpolate_anchor_torques(anchor_frames, anchor_path, args.frames)

    print("\nRefining and validating every final frame around the interpolated anchor path...")
    final_path = refine_final_path(decoded, library, recipes, tp_guess, ts_guess, args)

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    write_rows(output, final_path)
    write_rows(output.with_name(output.stem + "_anchor_stats.csv"), sorted(stats, key=lambda r: r["frame_no"]))
    preview = output.with_name(output.stem + "_preview.png")
    plot_preview(preview, final_path)

    utils = np.asarray([r["utilization_maxabs"] for r in final_path], dtype=float)
    print("\nLocked path ready. No lambda-plane maps were computed.")
    print(f"utilization range: {utils.min():.3f} .. {utils.max():.3f}; median={np.median(utils):.3f}")
    print(output)
    print(preview)
    print("\nUse it for the expensive animation only after you like the preview:")
    print(
        "python .\\studies\\closure-conditioning\\exploration/animate_controlled_free_shift_path.py "
        f"--path-csv \"{output}\" --resolution 641 --plot-limit 2.0 --jobs 8"
    )
    if not args.no_open:
        maybe_open(preview)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
