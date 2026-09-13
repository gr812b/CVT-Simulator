"""Build a compact review/share bundle from saved controlled-path closure maps.

This performs NO CINDER solves. It only reads the existing per-frame NPZ map files,
downsamples them, converts floating-point map fields to float32, copies the run CSV/GIF
metadata, and optionally keeps a few selected full-resolution core-map frames.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import zipfile
from pathlib import Path

import numpy as np

DEFAULT_FIELDS = (
    "lambda_p", "lambda_s", "R_p", "R_s", "cond_A_scaled", "rank_A",
    "sigma_min_J", "kappa_J", "det_J", "N_p", "N_s",
    "topology_failure_code", "topology_admissible",
    "static_capacity_admissible", "full_static_admissible",
)
DEFAULT_FULL_RES_FRAMES = (0, 30, 50, 58, 60, 61, 62, 65, 90, 119)


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-dir", type=Path, required=True)
    p.add_argument("--target-size", type=int, default=161)
    p.add_argument("--output-dir", type=Path, default=None)
    p.add_argument(
        "--full-res-frames", type=str,
        default=",".join(str(i) for i in DEFAULT_FULL_RES_FRAMES),
        help="Comma-separated 0-based frame indices to retain at full resolution. Empty string keeps none.",
    )
    p.add_argument("--fields", nargs="*", default=list(DEFAULT_FIELDS))
    p.add_argument("--no-zip", action="store_true")
    return p.parse_args()


def parse_frame_list(text: str) -> list[int]:
    text = text.strip()
    if not text:
        return []
    return sorted(set(int(x.strip()) for x in text.split(",") if x.strip()))


def nearest_indices(n: int, target: int) -> np.ndarray:
    if target <= 1:
        raise ValueError("--target-size must be at least 2.")
    if target >= n:
        return np.arange(n, dtype=int)
    return np.unique(np.rint(np.linspace(0, n - 1, target)).astype(int))


def convert_array(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr)
    if np.issubdtype(arr.dtype, np.floating):
        return arr.astype(np.float32, copy=False)
    return arr


def is_grid_field(arr: np.ndarray, ny: int, nx: int) -> bool:
    return arr.ndim == 2 and arr.shape == (ny, nx)


def read_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as data:
        return {k: np.asarray(data[k]) for k in data.files}


def core_payload(raw: dict[str, np.ndarray], fields: tuple[str, ...], *, target_size: int | None):
    if "lambda_p" not in raw or "lambda_s" not in raw:
        raise KeyError("Saved map is missing lambda_p/lambda_s.")
    lp = np.asarray(raw["lambda_p"])
    ls = np.asarray(raw["lambda_s"])
    nx, ny = lp.size, ls.size
    ix = np.arange(nx, dtype=int) if target_size is None else nearest_indices(nx, target_size)
    iy = np.arange(ny, dtype=int) if target_size is None else nearest_indices(ny, target_size)

    payload = {}
    for key in fields:
        if key not in raw:
            continue
        arr = np.asarray(raw[key])
        if key == "lambda_p":
            out = arr[ix]
        elif key == "lambda_s":
            out = arr[iy]
        elif is_grid_field(arr, ny, nx):
            out = arr[np.ix_(iy, ix)]
        else:
            out = arr
        payload[key] = convert_array(out)

    if "R_p" in payload and "R_s" in payload:
        payload["R_norm"] = np.hypot(
            payload["R_p"].astype(np.float32), payload["R_s"].astype(np.float32)
        ).astype(np.float32)

    for key, arr in raw.items():
        if key.startswith("actual__") or key.startswith("recipe__") or key in {"domain", "resolution"}:
            if np.asarray(arr).ndim == 0:
                payload[key] = np.asarray(arr)

    payload["share_target_size"] = np.asarray(int(len(ix)))
    payload["share_source_nx"] = np.asarray(int(nx))
    payload["share_source_ny"] = np.asarray(int(ny))
    payload["share_precision"] = np.asarray("float32_for_floating_maps")
    return payload


def copy_if_exists(src: Path, dst: Path):
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def write_manifest(path: Path, rows: list[dict]):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def zip_directory(directory: Path, zip_path: Path):
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(directory.parent))


def main():
    args = parse_args()
    source = args.source_dir.resolve()
    map_dir = source / "frames" / "map_data"
    if not map_dir.is_dir():
        raise FileNotFoundError(f"Missing saved map-data directory: {map_dir}")
    maps = sorted(map_dir.glob("map_*.npz"))
    if not maps:
        raise FileNotFoundError(f"No map_*.npz files found in {map_dir}")

    output = args.output_dir.resolve() if args.output_dir else source / f"share_bundle_{args.target_size}"
    if output.exists():
        shutil.rmtree(output)
    down_dir = output / "downsampled_maps"
    full_dir = output / "selected_full_resolution"
    down_dir.mkdir(parents=True, exist_ok=True)
    full_dir.mkdir(parents=True, exist_ok=True)

    requested_full = parse_frame_list(args.full_res_frames)
    fields = tuple(dict.fromkeys(args.fields))
    manifest = []
    total_source = total_down = total_full = 0

    print(f"Source: {source}")
    print(f"Maps: {len(maps)}")
    print(f"Target grid: {args.target_size}x{args.target_size}")
    print(f"Selected full-resolution frames: {requested_full or 'none'}")

    for k, map_path in enumerate(maps):
        raw = read_npz(map_path)
        total_source += map_path.stat().st_size
        down = core_payload(raw, fields, target_size=args.target_size)
        down_path = down_dir / map_path.name
        np.savez_compressed(down_path, **down)
        total_down += down_path.stat().st_size

        frame_no = int(map_path.stem.split("_")[-1])
        full_rel = ""
        if frame_no in requested_full:
            full = core_payload(raw, fields, target_size=None)
            fp = full_dir / map_path.name
            np.savez_compressed(fp, **full)
            total_full += fp.stat().st_size
            full_rel = str(fp.relative_to(output))

        manifest.append({
            "frame_no": frame_no,
            "source_file": map_path.name,
            "downsampled_file": str(down_path.relative_to(output)),
            "selected_full_resolution_file": full_rel,
            "source_bytes": map_path.stat().st_size,
            "downsampled_bytes": down_path.stat().st_size,
        })
        print(f"  {k+1:03d}/{len(maps):03d} {map_path.name}: "
              f"{map_path.stat().st_size/(1024**2):.1f} MiB -> {down_path.stat().st_size/(1024**2):.1f} MiB")

    copy_if_exists(source / "preflight_path.csv", output / "preflight_path.csv")
    copy_if_exists(source / "frame_summary.csv", output / "frame_summary.csv")
    for gif in source.glob("*.gif"):
        copy_if_exists(gif, output / gif.name)
    for png in source.glob("*.png"):
        copy_if_exists(png, output / png.name)

    write_manifest(output / "map_manifest.csv", manifest)
    summary = {
        "source_dir": str(source),
        "frame_count": len(maps),
        "target_grid_size": int(args.target_size),
        "fields": list(fields),
        "selected_full_resolution_frames": requested_full,
        "source_map_bytes": total_source,
        "downsampled_map_bytes": total_down,
        "selected_full_resolution_bytes": total_full,
        "notes": [
            "Review/share derivative only; keep original full-resolution maps locally.",
            "Floating map arrays are float32 in this bundle.",
            "R_norm is reconstructed from R_p and R_s.",
            "No CINDER solves are performed by this script.",
        ],
    }
    (output / "share_bundle_summary.json").write_text(json.dumps(summary, indent=2)+"\n", encoding="utf-8")
    (output / "README.md").write_text(
        "# Controlled free-shift closure-map share bundle\n\n"
        f"Frames: {len(maps)}\n\n"
        f"Downsampled grid: {args.target_size} x {args.target_size}\n\n"
        "Floating map precision: float32\n\n"
        "This bundle is derived entirely from already-saved NPZ maps; no closure maps were recomputed.\n",
        encoding="utf-8",
    )

    print("\nBundle directory:")
    print(output)
    print(f"Downsampled maps: {total_down/(1024**2):.1f} MiB; selected full-res: {total_full/(1024**2):.1f} MiB")
    if not args.no_zip:
        zip_path = output.with_suffix(".zip")
        if zip_path.exists():
            zip_path.unlink()
        zip_directory(output, zip_path)
        print("ZIP:")
        print(zip_path)
        print(f"ZIP size: {zip_path.stat().st_size/(1024**2):.1f} MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
