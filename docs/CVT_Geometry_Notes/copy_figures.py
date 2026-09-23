#!/usr/bin/env python3
"""Copy the figures required by CVT_Geometry_Notes.tex into its local figures/.

Run this script from anywhere:
    python docs/CVT_Geometry_Notes/copy_figures.py

The source artwork remains authoritative under
docs/CVT_Module_Formulation/figures/appendix/cvt_ratio_rate/.
This script copies only the six figures used by the companion geometry note.
"""

from __future__ import annotations

import shutil
from pathlib import Path


FIGURES = (
    "cvt_geometry_matched_side_by_side.png",
    "zoomed_out_R.png",
    "truncated_R.png",
    "ratio_rate_three_belts.png",
    "r_s.png",
    "r_p.png",
)


def main() -> None:
    note_dir = Path(__file__).resolve().parent
    docs_dir = note_dir.parent
    source_dir = (
        docs_dir
        / "CVT_Module_Formulation"
        / "figures"
        / "appendix"
        / "cvt_ratio_rate"
    )
    destination_dir = note_dir / "figures"

    missing = [source_dir / name for name in FIGURES if not (source_dir / name).is_file()]
    if missing:
        print("No figures were copied because required source files are missing:")
        for path in missing:
            print(f"  - {path}")
        raise SystemExit(1)

    destination_dir.mkdir(parents=True, exist_ok=True)

    for name in FIGURES:
        source = source_dir / name
        destination = destination_dir / name
        shutil.copy2(source, destination)
        print(f"Copied {source.relative_to(docs_dir.parent)} -> "
              f"{destination.relative_to(docs_dir.parent)}")

    print(f"\nReady: {len(FIGURES)} figures copied to "
          f"{destination_dir.relative_to(docs_dir.parent)}/")


if __name__ == "__main__":
    main()
