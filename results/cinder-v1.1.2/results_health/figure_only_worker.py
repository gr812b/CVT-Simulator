"""Isolated plotting worker for the CINDER v1.1.2 figure-only runner.

Each invocation handles exactly one study family.  Separate processes prevent
study-local ``analysis`` modules from colliding.  This worker contains no
simulation entry point and calls only retained-data publication functions.
"""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
RELEASE = HERE.parent

STUDIES = {
    "energy": RELEASE / "studies" / "energy-consistency",
    "solver": RELEASE / "studies" / "solver-convergence",
    "closure": RELEASE / "studies" / "closure-conditioning",
    "belt": RELEASE / "studies" / "reduced-belt-transients",
}


def load_publication_module(study: Path):
    # Put the study first so its generic ``analysis`` package is unambiguous.
    for item in (str(RELEASE), str(study)):
        while item in sys.path:
            sys.path.remove(item)
    sys.path.insert(0, str(RELEASE))
    sys.path.insert(0, str(study))
    return importlib.import_module("analysis.publication_plots")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family", choices=sorted(STUDIES), required=True)
    p.add_argument("--input-dir", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args()
    study = STUDIES[args.family]
    module = load_publication_module(study)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.family == "energy":
        result = module.publish(args.input_dir.resolve(), args.output_dir.resolve())
    elif args.family == "solver":
        result = module.publish(args.input_dir.resolve(), args.output_dir.resolve())
    elif args.family == "closure":
        result = module.build(args.input_dir.resolve(), args.output_dir.resolve())
    elif args.family == "belt":
        result = module.plot_all(args.input_dir.resolve(), args.output_dir.resolve())
    else:  # pragma: no cover
        raise AssertionError(args.family)
    print(json.dumps({"family": args.family, "result_type": type(result).__name__}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
