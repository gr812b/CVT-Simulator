"""Render additional panel GIFs for an existing controlled free-shift animation.

The original animation stores the resolved synthetic path in ``preflight_path.csv``
but does not store every 641x641 closure-map array.  Therefore this utility reuses
that exact resolved path (including per-frame shaft torques) and recomputes each
closure map once, then renders all requested panel GIFs from that one map evaluation.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, SymLogNorm, TwoSlopeNorm, ListedColormap
from matplotlib.patches import Rectangle
import numpy as np
from PIL import Image

import run as cc_run
from animate_controlled_free_shift_path import load_base, make_ref_and_sample

HERE = Path(__file__).resolve().parent
DEFAULT_INPUT = HERE / "artifacts" / "controlled-free-shift-animation"

_WORKER_DECODED = None
_WORKER_LIBRARY = None
_WORKER_RECIPES = None


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-dir", type=Path, default=None,
                   help="Directory containing preflight_path.csv/frame_summary.csv. Defaults to newest controlled run.")
    p.add_argument("--domain", choices=("physical", "expanded", "broad"), default=None,
                   help="Override map domain; normally inferred from source directory name.")
    p.add_argument("--resolution", type=int, default=None,
                   help="Override grid resolution; normally inferred from source directory name.")
    p.add_argument("--plot-limit", type=float, default=None)
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument("--fps", type=float, default=6.0)
    p.add_argument("--panels", nargs="*",
                   default=["Rp", "Rs", "Rnorm", "Acond", "Jmin", "Jcond", "Jdet", "N", "inadmissibility"],
                   help="Any of: Rp Rs Rnorm Acond Jmin Jcond Jdet N inadmissibility")
    p.add_argument("--keep-frames", action="store_true")
    p.add_argument("--force-recompute", action="store_true",
                   help="Ignore saved NPZ map data and recompute each frame from the stored path recipes.")
    p.add_argument("--no-open", action="store_true")
    return p.parse_args()


def newest_source_dir() -> Path:
    candidates = [p for p in DEFAULT_INPUT.glob("*") if p.is_dir() and (p / "preflight_path.csv").exists()]
    if not candidates:
        raise FileNotFoundError("No controlled-free-shift-animation artifact directory containing preflight_path.csv was found.")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def infer_domain_resolution(dirname: str):
    domain = None
    resolution = None
    for token in dirname.split("_"):
        if token in {"physical", "expanded", "broad"}:
            domain = token
        elif token.startswith("res"):
            try:
                resolution = int(token[3:])
            except ValueError:
                pass
    return domain, resolution


def _float_or_none(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    val = float(text)
    return None if math.isnan(val) else val


def load_recipes(path: Path) -> list[dict]:
    rows = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            rows.append({
                "frame_no": int(raw["frame_no"]),
                "leg": str(raw["leg"]),
                "shift_fraction": float(raw["shift_fraction"]),
                "shift_speed": float(raw["shift_speed"]),
                "target_primary_rpm": _float_or_none(raw.get("target_primary_rpm")),
                "target_belt_speed": _float_or_none(raw.get("target_belt_speed")),
                "primary_torque_Nm": float(raw["primary_torque_Nm"]),
                "secondary_torque_Nm": float(raw["secondary_torque_Nm"]),
            })
    rows.sort(key=lambda r: r["frame_no"])
    for expected, row in enumerate(rows):
        if row["frame_no"] != expected:
            raise RuntimeError(f"preflight_path.csv frame numbering is not contiguous at {expected}.")
    return rows


def positive_limits(values):
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a) & (a > 0)]
    if a.size == 0:
        return 1e-12, 1.0
    lo = max(float(np.percentile(a, 1)), 1e-16)
    hi = max(float(np.percentile(a, 99)), lo * 1.01)
    return lo, hi


def signed_limit(values):
    a = np.abs(np.asarray(values, dtype=float))
    a = a[np.isfinite(a)]
    return max(float(np.percentile(a, 99)) if a.size else 1.0, 1e-12)


def static_box(ref):
    law = ref.decoded.system.cvt.traction_law
    return (
        law.primary_static_interval.lower, law.primary_static_interval.upper,
        law.secondary_static_interval.lower, law.secondary_static_interval.upper,
    )


def panel_defs(data):
    normal = np.maximum(np.abs(data["N_p"]), np.abs(data["N_s"]))
    rp_lim = signed_limit(data["R_p"])
    rs_lim = signed_limit(data["R_s"])
    rn_lo, rn_hi = positive_limits(data["R_norm"])
    ca_lo, ca_hi = positive_limits(data["cond_A_scaled"])
    sm_lo, sm_hi = positive_limits(data["sigma_min_J"])
    kj_lo, kj_hi = positive_limits(data["kappa_J"])
    det_lim = signed_limit(data["det_J"])
    n_lo, n_hi = positive_limits(normal)
    return {
        "Rp": (r"Primary stick residual $R_p$", data["R_p"], SymLogNorm(linthresh=1.0, vmin=-rp_lim, vmax=rp_lim)),
        "Rs": (r"Secondary stick residual $R_s$", data["R_s"], SymLogNorm(linthresh=1.0, vmin=-rs_lim, vmax=rs_lim)),
        "Rnorm": (r"Residual norm $\|R\|_2$", data["R_norm"], LogNorm(vmin=rn_lo, vmax=rn_hi)),
        "Acond": (r"Equilibrated 8x8 $\kappa(A)$", data["cond_A_scaled"], LogNorm(vmin=ca_lo, vmax=ca_hi)),
        "Jmin": (r"$\sigma_{\min}(J_R)$", data["sigma_min_J"], LogNorm(vmin=sm_lo, vmax=sm_hi)),
        "Jcond": (r"$\kappa(J_R)$", data["kappa_J"], LogNorm(vmin=kj_lo, vmax=kj_hi)),
        "Jdet": (r"Signed $\det(J_R)$", data["det_J"], TwoSlopeNorm(vcenter=0.0, vmin=-det_lim, vmax=det_lim)),
        "N": (r"max$(|N_p|,|N_s|)$", normal, LogNorm(vmin=n_lo, vmax=n_hi)),
    }


def render_panel(data, actual, panel: str, path: Path, *, ref, domain: str, plot_limit: float | None):
    lp, ls = data["lambda_p"], data["lambda_s"]
    LP, LS = np.meshgrid(lp, ls)
    invalid = ~np.asarray(data["topology_admissible"], dtype=bool)

    if panel == "inadmissibility":
        code = np.asarray(data["topology_failure_code"], dtype=int)
        masks = [
            ("Admissible", code == 0),
            ("Neg. integrated normal", (code & 1) != 0),
            ("Neg. belt tension", (code & 2) != 0),
            ("Local wrap lift-off", (code & 4) != 0),
            ("Mechanism violation", (code & 8) != 0),
            ("Support would pull", (code & 16) != 0),
        ]
        fig, axes = plt.subplots(2, 3, figsize=(13.5, 8.8), constrained_layout=True)
        cmap = ListedColormap(["white", "black"])
        for ax, (title, mask) in zip(axes.ravel(), masks):
            ax.pcolormesh(LP, LS, mask.astype(int), shading="auto", cmap=cmap, vmin=0, vmax=1, rasterized=True)
            if domain != "physical":
                p0,p1,s0,s1 = static_box(ref)
                ax.add_patch(Rectangle((p0,s0), p1-p0, s1-s0, fill=False, linestyle=":", linewidth=1.1, edgecolor="tab:blue"))
            ax.plot(actual["lambda_p"], actual["lambda_s"], "x", markersize=7, mew=2, color="tab:red")
            ax.set_title(title)
            ax.set_xlabel(r"$\lambda_p$")
            ax.set_ylabel(r"$\lambda_s$")
            if plot_limit is not None:
                ax.set_xlim(-plot_limit, plot_limit)
                ax.set_ylim(-plot_limit, plot_limit)
        fig.suptitle(
            f"Inadmissibility breakdown | frame {actual['frame_no']+1:03d} | {actual['leg']} | "
            f"shift={actual['shift_fraction']:.3f} | primary={actual['primary_rpm']:.0f} rpm"
        )
    else:
        title, source, norm = panel_defs(data)[panel]
        values = np.ma.masked_where(invalid, np.asarray(source, dtype=float))
        fig, ax = plt.subplots(figsize=(9.2, 7.6))
        im = ax.pcolormesh(LP, LS, values, shading="auto", norm=norm, rasterized=True)
        if panel in {"Rp", "Rs", "Rnorm"}:
            try:
                if panel == "Rp":
                    ax.contour(LP, LS, data["R_p"], levels=[0.0], colors="black", linewidths=1.2)
                elif panel == "Rs":
                    ax.contour(LP, LS, data["R_s"], levels=[0.0], colors="black", linewidths=1.2, linestyles="--")
                else:
                    ax.contour(LP, LS, data["R_p"], levels=[0.0], colors="black", linewidths=1.2)
                    ax.contour(LP, LS, data["R_s"], levels=[0.0], colors="black", linewidths=1.2, linestyles="--")
            except ValueError:
                pass
        if domain != "physical":
            p0,p1,s0,s1 = static_box(ref)
            ax.add_patch(Rectangle((p0,s0), p1-p0, s1-s0, fill=False, linestyle=":", linewidth=1.2, edgecolor="black"))
        ax.plot(actual["lambda_p"], actual["lambda_s"], "x", markersize=9, mew=2.2, color="tab:red")
        ax.set_title(
            f"{title}\nframe {actual['frame_no']+1:03d} | {actual['leg']} | shift={actual['shift_fraction']:.3f} | "
            f"primary={actual['primary_rpm']:.0f} rpm | secondary={actual['secondary_rpm']:.0f} rpm"
        )
        ax.set_xlabel(r"$\lambda_p$")
        ax.set_ylabel(r"$\lambda_s$")
        if plot_limit is not None:
            ax.set_xlim(-plot_limit, plot_limit)
            ax.set_ylim(-plot_limit, plot_limit)
        fig.colorbar(im, ax=ax, label=title)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def assemble_gif(paths, outpath: Path, fps: float):
    frames = [Image.open(p).convert("P", palette=Image.ADAPTIVE) for p in paths]
    if not frames:
        raise RuntimeError("No frames were generated.")
    duration = max(1, int(round(1000.0 / max(fps, 1e-6))))
    frames[0].save(outpath, save_all=True, append_images=frames[1:], optimize=False, duration=duration, loop=0, disposal=2)
    for frame in frames:
        frame.close()



def read_frame_summary(path: Path) -> list[dict]:
    rows = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            cooked = {}
            for key, value in raw.items():
                if value is None:
                    cooked[key] = value
                    continue
                txt = str(value).strip()
                if txt == "":
                    cooked[key] = txt
                    continue
                try:
                    num = float(txt)
                    if txt.isdigit() or (txt.startswith("-") and txt[1:].isdigit()):
                        cooked[key] = int(num)
                    else:
                        cooked[key] = num
                except ValueError:
                    cooked[key] = txt
            rows.append(cooked)
    rows.sort(key=lambda r: int(r["frame_no"]))
    return rows


def load_saved_map(path: Path) -> dict:
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files if not k.startswith("actual__") and not k.startswith("recipe__") and k not in {"domain", "resolution"}}


def saved_map_path(source_dir: Path, frame_no: int) -> Path:
    return source_dir / "frames" / "map_data" / f"map_{frame_no:03d}.npz"

def worker_init(recipes: list[dict]):
    global _WORKER_DECODED, _WORKER_LIBRARY, _WORKER_RECIPES
    _WORKER_DECODED, _WORKER_LIBRARY = load_base()
    _WORKER_RECIPES = recipes


def frame_worker(frame_no: int, domain: str, resolution: int, plot_limit: float | None, panels: list[str], outdir: str, source_dir: str, summary_rows: list[dict], force_recompute: bool):
    recipe = _WORKER_RECIPES[frame_no]
    actual = dict(summary_rows[frame_no]) if summary_rows else {
        "frame_no": frame_no,
        "leg": recipe["leg"],
        "shift_fraction": float(recipe["shift_fraction"]),
    }
    map_path = saved_map_path(Path(source_dir), frame_no)
    ref = None
    if (not force_recompute) and map_path.exists():
        ref, _sample = make_ref_and_sample(_WORKER_DECODED, _WORKER_LIBRARY, recipe)
        data = load_saved_map(map_path)
    else:
        ref, sample = make_ref_and_sample(_WORKER_DECODED, _WORKER_LIBRARY, recipe)
        inspection = cc_run.reconstruct(ref, sample, closure_audit=True)
        contact = inspection.contact
        audit = inspection.closure_audit
        if contact is None or audit is None:
            raise RuntimeError(f"Frame {frame_no}: reconstructed state did not provide engaged closure diagnostics.")
        actual.setdefault("primary_rpm", sample.cvt_state.primary_angular_speed * 60.0 / (2.0 * math.pi))
        actual.setdefault("secondary_rpm", sample.cvt_state.secondary_angular_speed * 60.0 / (2.0 * math.pi))
        actual.setdefault("lambda_p", float(contact.traction_utilization.primary_lambda))
        actual.setdefault("lambda_s", float(contact.traction_utilization.secondary_lambda))
        data = cc_run.build_map(ref, sample, domain, resolution)

    root = Path(outdir)
    outputs = {}
    for panel in panels:
        path = root / panel / f"{panel}_{frame_no:03d}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        render_panel(data, actual, panel, path, ref=ref, domain=domain, plot_limit=plot_limit)
        outputs[panel] = str(path)
    return {"frame_no": frame_no, **outputs}


def main():
    args = parse_args()
    cc_run.verify_environment()
    source_dir = (args.source_dir or newest_source_dir()).resolve()
    preflight = source_dir / "preflight_path.csv"
    if not preflight.exists():
        raise FileNotFoundError(f"Missing {preflight}")
    recipes = load_recipes(preflight)
    summary_rows = read_frame_summary(source_dir / "frame_summary.csv") if (source_dir / "frame_summary.csv").exists() else []
    inferred_domain, inferred_resolution = infer_domain_resolution(source_dir.name)
    domain = args.domain or inferred_domain or "expanded"
    resolution = int(args.resolution or inferred_resolution or 641)
    panels = list(dict.fromkeys(args.panels))
    valid = {"Rp", "Rs", "Rnorm", "Acond", "Jmin", "Jcond", "Jdet", "N", "inadmissibility"}
    invalid = [p for p in panels if p not in valid]
    if invalid:
        raise ValueError(f"Unknown panels: {invalid}")

    outdir = source_dir / "derived_panel_gifs"
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"Source path: {source_dir}")
    print(f"Reusing {len(recipes)} resolved preflight states; NO torque/path search will be rerun.")
    map_dir = source_dir / "frames" / "map_data"
    has_saved = map_dir.exists() and any(map_dir.glob("map_*.npz"))
    if has_saved and not args.force_recompute:
        print(f"Using saved per-frame NPZ map data from {map_dir} when available.")
    else:
        print(f"Recomputing closure maps once per frame: {domain}, {resolution}x{resolution}, jobs={args.jobs}")
    print(f"Rendering from each map: {', '.join(panels)}")

    rendered = []
    with ProcessPoolExecutor(max_workers=max(1, int(args.jobs)), initializer=worker_init, initargs=(recipes,)) as ex:
        futures = [
            ex.submit(frame_worker, i, domain, resolution, args.plot_limit, panels, str(outdir), str(source_dir), summary_rows, args.force_recompute)
            for i in range(len(recipes))
        ]
        for future in as_completed(futures):
            row = future.result()
            rendered.append(row)
            print(f"  finished frame {row['frame_no']+1}/{len(recipes)}")
    rendered.sort(key=lambda row: row["frame_no"])

    gifs = []
    for panel in panels:
        paths = [Path(row[panel]) for row in rendered]
        gif = outdir / f"controlled_free_shift_{domain}_{panel}.gif"
        assemble_gif(paths, gif, args.fps)
        gifs.append((panel, gif))
        print(gif)
        if not args.keep_frames:
            for path in paths:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass

    manifest = outdir / "generated_gifs.csv"
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["panel", "gif_path"])
        writer.writerows((panel, str(path)) for panel, path in gifs)
    print(manifest)
    if not args.no_open:
        for _panel, path in gifs[:4]:
            maybe_open(path)
    return 0


def maybe_open(path: Path):
    try:
        if hasattr(os, "startfile"):
            os.startfile(str(path))  # type: ignore[attr-defined]
    except Exception:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
