"""Animate closure maps along a deliberately controlled free-shift stick-stick path.

This is a synthetic diagnostic, not a vehicle simulation.  Shift position and speed
(and optionally primary RPM) are prescribed.  A fixed-boundary bench is then chosen
for each frame so that the requested instantaneous state is genuinely classified as
engaged / FREE / STICK_STICK and passes the same physical-admissibility checks used
by the shared operating-case library.

The important point is that the target kinematics are never silently moved to make a
frame work.  If the initially preferred shaft torques do not support the requested
stick-stick state, the script searches the shared fixed-boundary torque space and keeps
the closest admissible torque pair.  Only then are the expensive lambda maps launched
in parallel.
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
from matplotlib.colors import LogNorm
from matplotlib.patches import Rectangle
import numpy as np
from PIL import Image

import run as cc_run
from case_library import (
    admissible_stick_snapshot,
    full_state,
    load_case_library,
    make_bench_system,
    zero_relative_speed_state,
)
from cinder.execution.hybrid.cvt_regime import CVTEngagementState, CVTShiftConstraint
from cinder.model.cvt.contact import EngagedContactMode

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts" / "controlled-free-shift-animation"

_WORKER_DECODED = None
_WORKER_LIBRARY = None


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--domain", choices=("physical", "expanded", "broad"), default="expanded")
    p.add_argument("--resolution", type=int, default=None,
                   help="Grid points per axis. Defaults: physical=241, expanded=641, broad=1001.")
    p.add_argument("--plot-limit", type=float, default=2.0)
    p.add_argument("--frames", type=int, default=60)
    p.add_argument("--path-csv", type=Path, default=None,
                   help="Use a previously locked path CSV and skip the torque/path preflight search entirely.")
    p.add_argument("--fps", type=float, default=6.0)
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument("--shift-start", type=float, default=0.30)
    p.add_argument("--shift-end", type=float, default=0.70)
    p.add_argument("--shift-speed-mm-s", type=float, default=20.0)

    # The known-good shared free-shift cases live around 12--16 m/s.  These are
    # deliberately conservative defaults; wider sweeps can be requested explicitly.
    p.add_argument("--belt-speed-start", type=float, default=12.0)
    p.add_argument("--belt-speed-end", type=float, default=16.0)

    # Optional primary-RPM-controlled path.  If supplied, these replace the belt-speed
    # targets; belt speed is solved so the no-relative-speed state hits the requested RPM.
    p.add_argument("--primary-rpm-start", type=float, default=None)
    p.add_argument("--primary-rpm-end", type=float, default=None)

    p.add_argument("--preferred-primary-torque", type=float, default=0.0)
    p.add_argument("--preferred-secondary-torque", type=float, default=0.0)
    p.add_argument("--torque-search-limit", type=float, default=40.0,
                   help="Fallback torque-search limit [Nm], searched in 5 Nm increments.")
    p.add_argument("--keep-frames", action="store_true")
    p.add_argument("--save-map-data", action="store_true", default=True,
                   help="Save each full closure map as compressed NPZ so later panel renders do not need to recompute.")
    p.add_argument("--no-save-map-data", dest="save_map_data", action="store_false",
                   help="Disable saving per-frame compressed map data.")
    p.add_argument("--no-open", action="store_true")
    return p.parse_args()


def default_resolution(domain: str) -> int:
    return {"physical": 241, "expanded": 641, "broad": 1001}[domain]


def load_base():
    spec = cc_run.load_json(cc_run.SPEC_FILE)
    base = (cc_run.HERE / spec["base_document"]).resolve()
    decoded = cc_run.validate_and_decode(cc_run.load_json(base))
    library = load_case_library(cc_run.CASE_LIBRARY_FILE)
    return decoded, library


def frame_recipe(i: int, n: int, args) -> dict:
    n_up = n // 2 + 1
    if i < n_up:
        tau = 0.0 if n_up == 1 else i / (n_up - 1)
        leg = "upshift"
        sfrac = (1.0 - tau) * args.shift_start + tau * args.shift_end
        direction = +1.0
    else:
        n_down = n - n_up
        k = i - n_up + 1
        tau = 1.0 if n_down <= 0 else k / n_down
        leg = "backshift"
        sfrac = (1.0 - tau) * args.shift_end + tau * args.shift_start
        direction = -1.0

    # Make the turnaround frame exactly zero shift speed instead of instantaneously
    # jumping from +v to -v at the same state.
    if i == n_up - 1:
        sdot = 0.0
    else:
        sdot = direction * abs(args.shift_speed_mm_s) / 1000.0

    use_rpm = args.primary_rpm_start is not None or args.primary_rpm_end is not None
    if use_rpm:
        if args.primary_rpm_start is None or args.primary_rpm_end is None:
            raise ValueError("Supply both --primary-rpm-start and --primary-rpm-end.")
        if leg == "upshift":
            target = (1.0 - tau) * args.primary_rpm_start + tau * args.primary_rpm_end
        else:
            target = (1.0 - tau) * args.primary_rpm_end + tau * args.primary_rpm_start
        return {
            "frame_no": i, "leg": leg, "shift_fraction": float(sfrac),
            "shift_speed": float(sdot), "target_primary_rpm": float(target),
            "target_belt_speed": None,
        }

    if leg == "upshift":
        target = (1.0 - tau) * args.belt_speed_start + tau * args.belt_speed_end
    else:
        target = (1.0 - tau) * args.belt_speed_end + tau * args.belt_speed_start
    return {
        "frame_no": i, "leg": leg, "shift_fraction": float(sfrac),
        "shift_speed": float(sdot), "target_primary_rpm": None,
        "target_belt_speed": float(target),
    }


def state_for_recipe(system, recipe: dict):
    gs = system.cvt.model.geometry.spec
    shift = gs.deadzone_shift + float(recipe["shift_fraction"]) * (gs.max_shift - gs.deadzone_shift)
    if recipe["target_primary_rpm"] is None:
        return zero_relative_speed_state(
            system,
            shift=shift,
            shift_speed=float(recipe["shift_speed"]),
            belt_speed=float(recipe["target_belt_speed"]),
        )

    omega_target = float(recipe["target_primary_rpm"]) * (2.0 * math.pi / 60.0)
    geom = system.cvt.model.geometry.evaluate_engaged(float(shift))
    vb = omega_target * geom.primary.effective
    # zero_relative_speed_state includes the representative contact-speed correction
    # from shift motion, so iterate on vb until the requested shaft RPM is reached.
    cvt = None
    for _ in range(5):
        cvt = zero_relative_speed_state(
            system,
            shift=shift,
            shift_speed=float(recipe["shift_speed"]),
            belt_speed=float(vb),
        )
        vb += (omega_target - cvt.primary_angular_speed) * geom.primary.effective
    assert cvt is not None
    return cvt


def candidate_torque_pairs(library: dict, args, previous: tuple[float, float] | None):
    bench = library["fixed_boundary_bench"]
    base_p = {float(v) for v in bench["primary_torques_Nm"]}
    base_s = {float(v) for v in bench["secondary_torques_Nm"]}
    limit = abs(float(args.torque_search_limit))
    dense = np.arange(-limit, limit + 2.5, 5.0)
    base_p.update(float(v) for v in dense)
    base_s.update(float(v) for v in dense)
    base_p.add(float(args.preferred_primary_torque))
    base_s.add(float(args.preferred_secondary_torque))

    ppref = float(args.preferred_primary_torque)
    spref = float(args.preferred_secondary_torque)
    if previous is None:
        previous = (ppref, spref)
    pprev, sprev = previous

    pairs = [(p, s) for p in base_p for s in base_s]
    # Continuity first, then proximity to the requested nominal boundary, then load.
    pairs.sort(key=lambda ps: (
        abs(ps[0] - pprev) + abs(ps[1] - sprev),
        0.35 * (abs(ps[0] - ppref) + abs(ps[1] - spref)),
        0.05 * (abs(ps[0]) + abs(ps[1])),
    ))
    return pairs


def classify_candidate(decoded, library: dict, recipe: dict, tp: float, ts: float):
    system = make_bench_system(decoded, library, primary_torque=tp, secondary_torque=ts)
    cvt = state_for_recipe(system, recipe)
    state = full_state(system, cvt)
    try:
        mode = system.classify_initial_mode(state)
    except Exception as exc:
        return None, {"reason": f"{type(exc).__name__}: {exc}"}
    try:
        ok, diag = admissible_stick_snapshot(system, state=state, mode=mode, library=library)
    except Exception as exc:
        return None, {"reason": f"{type(exc).__name__}: {exc}"}
    if not ok:
        return None, diag
    cm = mode.cvt
    exact = (
        cm.engagement is CVTEngagementState.ENGAGED
        and cm.shift_constraint is CVTShiftConstraint.FREE
        and cm.contact_regime is not None
        and cm.contact_regime.mode is EngagedContactMode.STICK_STICK
    )
    if not exact:
        return None, {"reason": "accepted_by_snapshot_but_not_exact_free_stick_stick"}
    return (system, cvt, state, mode), diag


def preflight_path(decoded, library: dict, recipes: list[dict], args):
    print("Preflighting the requested kinematic path and choosing admissible shaft-boundary torques...")
    previous = None
    resolved = []
    for i, recipe in enumerate(recipes):
        chosen = None
        last_reason = None
        for tp, ts in candidate_torque_pairs(library, args, previous):
            result, diag = classify_candidate(decoded, library, recipe, tp, ts)
            if result is not None:
                system, cvt, state, mode = result
                chosen = {
                    **recipe,
                    "primary_torque_Nm": float(tp),
                    "secondary_torque_Nm": float(ts),
                    "resolved_belt_speed_m_s": float(cvt.belt_speed),
                    "resolved_primary_rpm": float(cvt.primary_angular_speed * 60.0 / (2.0 * math.pi)),
                    "resolved_secondary_rpm": float(cvt.secondary_angular_speed * 60.0 / (2.0 * math.pi)),
                    "preflight_lambda_p": float(diag["lambda_p"]),
                    "preflight_lambda_s": float(diag["lambda_s"]),
                    "preflight_scaled_condition_A": float(diag["scaled_condition_A"]),
                }
                previous = (float(tp), float(ts))
                break
            last_reason = diag.get("reason", "unknown")
        if chosen is None:
            target = (
                f"primary_rpm={recipe['target_primary_rpm']:.3f}"
                if recipe["target_primary_rpm"] is not None
                else f"belt_speed={recipe['target_belt_speed']:.3f} m/s"
            )
            raise RuntimeError(
                f"No admissible FREE/STICK_STICK boundary was found for frame {i}: "
                f"shift_fraction={recipe['shift_fraction']:.4f}, {target}, "
                f"shift_speed={1000*recipe['shift_speed']:.3f} mm/s. "
                f"Last rejection: {last_reason}. Increase --torque-search-limit or narrow the path."
            )
        resolved.append(chosen)
        print(
            f"  frame {i+1:03d}/{len(recipes)} {chosen['leg']:<9s} "
            f"shift={chosen['shift_fraction']:.3f} rpm_p={chosen['resolved_primary_rpm']:.0f} "
            f"Tp={chosen['primary_torque_Nm']:+.0f} Ts={chosen['secondary_torque_Nm']:+.0f} "
            f"lambda=({chosen['preflight_lambda_p']:+.3f},{chosen['preflight_lambda_s']:+.3f})"
        )
    return resolved


def make_ref_and_sample(decoded, library: dict, recipe: dict):
    system = make_bench_system(
        decoded, library,
        primary_torque=float(recipe["primary_torque_Nm"]),
        secondary_torque=float(recipe["secondary_torque_Nm"]),
    )
    cvt = state_for_recipe(system, recipe)
    state = full_state(system, cvt)
    mode = system.classify_initial_mode(state)
    ref = SimpleNamespace(
        name="controlled_free_shift",
        decoded=SimpleNamespace(system=system),
        result=None,
        samples=tuple(),
    )
    sample = cc_run.FrozenSample(
        time=float(recipe["frame_no"]),
        full_state=state,
        composed_mode=mode,
        cvt_state=cvt,
    )
    return ref, sample


def positive_limits(values):
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a) & (a > 0)]
    if a.size == 0:
        return 1e-12, 1.0
    lo = max(float(np.percentile(a, 1)), 1e-16)
    hi = max(float(np.percentile(a, 99.8)), lo * 1.01)
    return lo, hi


def static_box(ref):
    law = ref.decoded.system.cvt.traction_law
    return (
        law.primary_static_interval.lower, law.primary_static_interval.upper,
        law.secondary_static_interval.lower, law.secondary_static_interval.upper,
    )


def overlay_plot(data, actual, path: Path, *, ref, domain: str, mask_overlay: bool, plot_limit: float | None):
    lp, ls = data["lambda_p"], data["lambda_s"]
    LP, LS = np.meshgrid(lp, ls)
    cond = np.asarray(data["cond_A_scaled"], float)
    invalid = ~np.asarray(data["topology_admissible"], bool)
    fig, ax = plt.subplots(figsize=(9.2, 7.6))
    lo, hi = positive_limits(cond)
    im = ax.pcolormesh(LP, LS, cond, shading="auto", norm=LogNorm(vmin=lo, vmax=hi), rasterized=True)
    if mask_overlay:
        ax.contourf(LP, LS, invalid.astype(float), levels=[0.5, 1.5], colors=["0.7"], alpha=0.34)
    try:
        ax.contour(LP, LS, data["R_p"], levels=[0.0], colors="black", linewidths=1.25)
        ax.contour(LP, LS, data["R_s"], levels=[0.0], colors="black", linewidths=1.25, linestyles="--")
    except ValueError:
        pass
    if domain != "physical":
        p0, p1, s0, s1 = static_box(ref)
        ax.add_patch(Rectangle((p0, s0), p1-p0, s1-s0, fill=False, linestyle=":", linewidth=1.2, edgecolor="tab:blue"))
    ax.plot(actual["lambda_p"], actual["lambda_s"], "x", markersize=10, mew=2.4, color="tab:red")
    ax.set_title(
        "Controlled free-shift stick-stick path\n"
        f"frame {actual['frame_no']+1:03d} | {actual['leg']} | shift={actual['shift_fraction']:.3f} | "
        f"primary={actual['primary_rpm']:.0f} rpm | secondary={actual['secondary_rpm']:.0f} rpm\n"
        f"Tp={actual['primary_torque_Nm']:+.0f} Nm, Ts={actual['secondary_torque_Nm']:+.0f} Nm | "
        f"root=({actual['lambda_p']:+.3f},{actual['lambda_s']:+.3f}) | scaled kappa(A)={actual['A_condition_scaled']:.3g}"
    )
    ax.set_xlabel(r"$\lambda_p$")
    ax.set_ylabel(r"$\lambda_s$")
    if plot_limit is not None:
        ax.set_xlim(-plot_limit, plot_limit)
        ax.set_ylim(-plot_limit, plot_limit)
    fig.colorbar(im, ax=ax, label=r"equilibrated $\kappa(A)$")
    fig.tight_layout()
    fig.savefig(path, dpi=190)
    plt.close(fig)


def worker_init():
    global _WORKER_DECODED, _WORKER_LIBRARY
    # Parent performs the full environment verification once.  Workers only decode the
    # frozen document, avoiding eight copies of the verbose environment banner on Windows.
    _WORKER_DECODED, _WORKER_LIBRARY = load_base()


def frame_worker(recipe: dict, domain: str, resolution: int, plot_limit: float | None, outdir: str, save_map_data_flag: bool):
    ref, sample = make_ref_and_sample(_WORKER_DECODED, _WORKER_LIBRARY, recipe)
    inspection = cc_run.reconstruct(ref, sample, closure_audit=True)
    contact = inspection.contact
    audit = inspection.closure_audit
    if contact is None or audit is None:
        raise RuntimeError(f"Frame {recipe['frame_no']} failed reconstruction after successful preflight.")
    actual = {
        "frame_no": int(recipe["frame_no"]),
        "leg": recipe["leg"],
        "shift_fraction": float(recipe["shift_fraction"]),
        "shift_mm": 1000.0 * sample.cvt_state.shift_position,
        "shift_speed_mm_s": 1000.0 * sample.cvt_state.shift_speed,
        "belt_speed_m_s": sample.cvt_state.belt_speed,
        "primary_rpm": sample.cvt_state.primary_angular_speed * 60.0 / (2.0 * math.pi),
        "secondary_rpm": sample.cvt_state.secondary_angular_speed * 60.0 / (2.0 * math.pi),
        "primary_torque_Nm": float(recipe["primary_torque_Nm"]),
        "secondary_torque_Nm": float(recipe["secondary_torque_Nm"]),
        "lambda_p": float(contact.traction_utilization.primary_lambda),
        "lambda_s": float(contact.traction_utilization.secondary_lambda),
        "A_condition_scaled": float(audit.scaled_condition_number),
        "A_rank": int(audit.matrix_rank),
    }
    data = cc_run.build_map(ref, sample, domain, resolution)
    root = Path(outdir)
    if save_map_data_flag:
        save_map_data(root / "map_data" / f"map_{recipe['frame_no']:03d}.npz", data, actual, recipe, domain=domain, resolution=resolution)
    masked = root / f"masked_{recipe['frame_no']:03d}.png"
    raw = root / f"raw_{recipe['frame_no']:03d}.png"
    overlay_plot(data, actual, masked, ref=ref, domain=domain, mask_overlay=True, plot_limit=plot_limit)
    overlay_plot(data, actual, raw, ref=ref, domain=domain, mask_overlay=False, plot_limit=plot_limit)
    return {"masked": str(masked), "raw": str(raw), **actual}


def write_rows(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
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


def assemble_gif(paths, outpath: Path, fps: float):
    frames = [Image.open(p).convert("P", palette=Image.ADAPTIVE) for p in paths]
    if not frames:
        raise RuntimeError("No frames generated.")
    duration = max(1, int(round(1000.0 / max(fps, 1e-6))))
    frames[0].save(outpath, save_all=True, append_images=frames[1:], optimize=False,
                   duration=duration, loop=0, disposal=2)
    for frame in frames:
        frame.close()


def maybe_open(path: Path):
    try:
        if hasattr(os, "startfile"):
            os.startfile(str(path))  # type: ignore[attr-defined]
    except Exception:
        pass



def save_map_data(path: Path, data: dict, actual: dict, recipe: dict, *, domain: str, resolution: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "domain": np.asarray(domain),
        "resolution": np.asarray(int(resolution)),
    }
    for key, value in data.items():
        payload[key] = np.asarray(value)
    for prefix, src in (("actual", actual), ("recipe", recipe)):
        for key, value in src.items():
            if isinstance(value, (str, bytes)):
                payload[f"{prefix}__{key}"] = np.asarray(str(value))
            elif value is None:
                payload[f"{prefix}__{key}"] = np.asarray("None")
            else:
                payload[f"{prefix}__{key}"] = np.asarray(value)
    np.savez_compressed(path, **payload)


def _optional_float(text):
    if text is None:
        return None
    value = str(text).strip()
    if not value or value.lower() in {"none", "nan"}:
        return None
    return float(value)


def load_locked_path(path: Path) -> list[dict]:
    required = {
        "frame_no", "leg", "shift_fraction", "shift_speed",
        "primary_torque_Nm", "secondary_torque_Nm",
    }
    rows = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            missing = required.difference(raw)
            if missing:
                raise ValueError(f"Locked path is missing required columns: {sorted(missing)}")
            rows.append({
                **raw,
                "frame_no": int(raw["frame_no"]),
                "leg": str(raw["leg"]),
                "shift_fraction": float(raw["shift_fraction"]),
                "shift_speed": float(raw["shift_speed"]),
                "target_primary_rpm": _optional_float(raw.get("target_primary_rpm")),
                "target_belt_speed": _optional_float(raw.get("target_belt_speed")),
                "primary_torque_Nm": float(raw["primary_torque_Nm"]),
                "secondary_torque_Nm": float(raw["secondary_torque_Nm"]),
            })
    rows.sort(key=lambda r: r["frame_no"])
    for expected, row in enumerate(rows):
        if row["frame_no"] != expected:
            raise ValueError(f"Locked path frame numbering is not contiguous at {expected}.")
    if not rows:
        raise ValueError("Locked path CSV is empty.")
    return rows

def main():
    args = parse_args()
    cc_run.verify_environment()
    decoded, library = load_base()
    if args.path_csv is not None:
        locked = args.path_csv.resolve()
        resolved = load_locked_path(locked)
        print(f"Using locked path with {len(resolved)} frames: {locked}")
        print("Skipping torque/path preflight search entirely.")
        run_tag = f"locked_{locked.stem}"
    else:
        recipes = [frame_recipe(i, args.frames, args) for i in range(args.frames)]
        resolved = preflight_path(decoded, library, recipes, args)
        run_tag = f"frames{args.frames}"

    resolution = int(args.resolution or default_resolution(args.domain))
    outdir = ARTIFACTS / f"{args.domain}_res{resolution}_{run_tag}"
    frame_dir = outdir / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    write_rows(outdir / "preflight_path.csv", resolved)

    print(f"\nAll {len(resolved)} target states are admissible FREE/STICK_STICK.")
    print(f"Launching {resolution}x{resolution} maps with {args.jobs} worker processes...")
    rows = []
    with ProcessPoolExecutor(max_workers=max(1, int(args.jobs)), initializer=worker_init) as ex:
        futures = [
            ex.submit(frame_worker, recipe, args.domain, resolution, args.plot_limit, str(frame_dir), args.save_map_data)
            for recipe in resolved
        ]
        for fut in as_completed(futures):
            row = fut.result()
            rows.append(row)
            print(
                f"  finished {row['frame_no']+1:03d}/{len(resolved)} | {row['leg']:<9s} | "
                f"primary={row['primary_rpm']:.0f} rpm | root=({row['lambda_p']:+.3f},{row['lambda_s']:+.3f})"
            )
    rows.sort(key=lambda r: r["frame_no"])
    write_rows(outdir / "frame_summary.csv", rows)

    masked_paths = [Path(r["masked"]) for r in rows]
    raw_paths = [Path(r["raw"]) for r in rows]
    masked_gif = outdir / f"controlled_free_shift_{args.domain}_masked.gif"
    raw_gif = outdir / f"controlled_free_shift_{args.domain}_raw.gif"
    assemble_gif(masked_paths, masked_gif, args.fps)
    assemble_gif(raw_paths, raw_gif, args.fps)

    print("\nOutputs:")
    print(masked_gif)
    print(raw_gif)
    print(outdir / "preflight_path.csv")
    print(outdir / "frame_summary.csv")
    if args.save_map_data:
        print(outdir / "frames" / "map_data")
    if not args.keep_frames:
        for p in masked_paths + raw_paths:
            try:
                p.unlink()
            except FileNotFoundError:
                pass
    if not args.no_open:
        maybe_open(masked_gif)
        maybe_open(raw_gif)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
