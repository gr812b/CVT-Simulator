r"""High-resolution far-out mid-shift closure map for CINDER v1.1.2.

Drop this file into:
    results/cinder-v1.1.2/studies/mechanical-invariants/

It reuses the sibling closure-conditioning study's *actual* map construction,
so the mechanics/admissibility tests stay identical to the release study.  It
only changes the broad lambda-domain resolution and plotting presentation.

Examples (from results/cinder-v1.1.2):
    python .\studies\mechanical-invariants\highres_midshift_closure_map.py --resolution 1001
    python .\studies\mechanical-invariants\highres_midshift_closure_map.py --resolution 1501 --limit 10

Outputs are written beside this script under:
    artifacts/highres_midshift_closure/

Two main figures are produced and opened automatically on Windows:
  * mid_shift_farout_with_admissibility.png
  * mid_shift_farout_raw.png

The complete unmasked numerical grid is retained in mid_shift_farout_map.npz.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resolution",
        type=int,
        default=1001,
        help="Grid points per lambda axis. 501 matches the main study; 1001 is ~4x as many grid points.",
    )
    parser.add_argument(
        "--limit",
        type=float,
        default=10.0,
        help="Symmetric lambda half-width. Default gives [-10,+10] on both axes.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=320,
        help="Saved figure DPI.",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open the finished PNGs in the system image viewer.",
    )
    return parser.parse_args()


def load_closure_study(mechanical_dir: Path):
    closure_dir = mechanical_dir.parent / "closure-conditioning"
    run_file = closure_dir / "run.py"
    if not run_file.is_file():
        raise FileNotFoundError(
            f"Could not find sibling closure-conditioning study at {run_file}"
        )

    # run.py imports its local conditioning_math.py and case_library.py by name.
    sys.path.insert(0, str(closure_dir))
    spec = importlib.util.spec_from_file_location("cinder_closure_conditioning_run", run_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import {run_file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def open_file(path: Path) -> None:
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as exc:
        print(f"Could not automatically open {path.name}: {exc}")


def plot_overlay(cc, data, actual, ref, path: Path, *, limit: float, dpi: int, show_admissibility: bool) -> None:
    # Use the same visual language as closure-conditioning/plot_feature_overlay,
    # but allow an otherwise-identical raw view without the gray admissibility overlay.
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm
    from matplotlib.patches import Rectangle

    lp = np.asarray(data["lambda_p"], dtype=float)
    ls = np.asarray(data["lambda_s"], dtype=float)
    LP, LS = np.meshgrid(lp, ls)
    cond = np.asarray(data["cond_A_scaled"], dtype=float)
    invalid = ~np.asarray(data["topology_admissible"], dtype=bool)

    finite = cond[np.isfinite(cond) & (cond > 0.0)]
    if finite.size == 0:
        raise RuntimeError("No finite positive 8x8 condition numbers were computed.")
    lo = max(float(np.nanpercentile(finite, 1.0)), 1.0)
    hi = max(float(np.nanpercentile(finite, 99.8)), lo * 1.01)

    fig, ax = plt.subplots(figsize=(11.5, 9.5))
    im = ax.pcolormesh(
        LP,
        LS,
        cond,
        shading="auto",
        norm=LogNorm(vmin=lo, vmax=hi),
        rasterized=True,
    )

    if show_admissibility:
        # Gray means the calculation exists but the retained mechanical topology
        # is inadmissible at that trial traction pair.
        ax.contourf(
            LP,
            LS,
            invalid.astype(float),
            levels=[0.5, 1.5],
            colors=["0.72"],
            alpha=0.34,
        )

    # Primary solid, secondary dashed: same convention as the release study.
    ax.contour(LP, LS, data["R_p"], levels=[0.0], colors="black", linewidths=1.25)
    ax.contour(
        LP,
        LS,
        data["R_s"],
        levels=[0.0],
        colors="black",
        linewidths=1.25,
        linestyles="--",
    )

    p0, p1, s0, s1 = cc._static_box(ref)
    ax.add_patch(
        Rectangle(
            (p0, s0),
            p1 - p0,
            s1 - s0,
            fill=False,
            linestyle=":",
            linewidth=1.8,
            edgecolor="tab:blue",
        )
    )
    ax.plot(
        actual["lambda_p"],
        actual["lambda_s"],
        "x",
        markersize=11,
        mew=2.6,
        color="tab:red",
        label="actual mid-shift root",
    )

    subtitle = "with topology inadmissibility" if show_admissibility else "all computed points (no admissibility overlay)"
    ax.set_title(
        f"mid_shift: high-resolution closure ridges and zero contours\n"
        f"$\\lambda_p,\\lambda_s\\in[-{limit:g},{limit:g}]$ — {subtitle}"
    )
    ax.set_xlabel(r"$\lambda_p$")
    ax.set_ylabel(r"$\lambda_s$")
    ax.set_xlim(-limit, limit)
    ax.set_ylim(-limit, limit)
    ax.legend(loc="best")
    fig.colorbar(im, ax=ax, label=r"equilibrated $\kappa(A)$")
    fig.tight_layout()
    fig.savefig(path, dpi=dpi)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    if args.resolution < 51:
        raise ValueError("--resolution must be at least 51.")
    if args.limit <= 0.0:
        raise ValueError("--limit must be positive.")

    mechanical_dir = Path(__file__).resolve().parent
    cc = load_closure_study(mechanical_dir)
    cc.verify_environment()

    study_spec = cc.load_json(cc.SPEC_FILE)
    print("Building frozen nominal launch and selecting mid_shift...")
    launch = cc.build_reference(study_spec, "launch")
    selected = {label: (ref, sample) for label, ref, sample in cc.select_nominal_states(launch)}
    if "mid_shift" not in selected:
        raise RuntimeError("The nominal launch did not produce a mid_shift stick-stick state.")
    ref, sample = selected["mid_shift"]
    actual = cc.actual_root_metrics("mid_shift", ref, sample)

    # Reuse the production study's broad-map function but make the half-width configurable.
    original_domain_bounds = cc.domain_bounds

    def custom_domain_bounds(reference, domain: str):
        if domain == "broad":
            return -args.limit, args.limit, -args.limit, args.limit
        return original_domain_bounds(reference, domain)

    cc.domain_bounds = custom_domain_bounds

    print(
        f"Computing {args.resolution} x {args.resolution} = "
        f"{args.resolution * args.resolution:,} trial closures over "
        f"[-{args.limit:g}, +{args.limit:g}]^2 ..."
    )
    data = cc.build_map(ref, sample, "broad", int(args.resolution))

    out = mechanical_dir / "artifacts" / "highres_midshift_closure"
    out.mkdir(parents=True, exist_ok=True)
    npz = out / "mid_shift_farout_map.npz"
    np.savez_compressed(npz, **data)

    masked = out / "mid_shift_farout_with_admissibility.png"
    raw = out / "mid_shift_farout_raw.png"
    reasons = out / "mid_shift_farout_inadmissibility_breakdown.png"

    plot_overlay(
        cc,
        data,
        actual,
        ref,
        masked,
        limit=args.limit,
        dpi=args.dpi,
        show_admissibility=True,
    )
    plot_overlay(
        cc,
        data,
        actual,
        ref,
        raw,
        limit=args.limit,
        dpi=args.dpi,
        show_admissibility=False,
    )
    cc.plot_inadmissibility(data, actual, "mid_shift", "broad", reasons, ref=ref)

    admissible = int(np.count_nonzero(data["topology_admissible"]))
    total = int(data["topology_admissible"].size)
    print("\nFinished.")
    print(f"  topology-admissible: {admissible:,}/{total:,} ({100.0*admissible/total:.3f}%)")
    print(f"  with admissibility: {masked}")
    print(f"  raw:                {raw}")
    print(f"  reasons:            {reasons}")
    print(f"  raw numerical grid: {npz}")

    if not args.no_open:
        open_file(masked)
        open_file(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
