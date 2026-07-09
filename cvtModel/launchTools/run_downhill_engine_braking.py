from __future__ import annotations

import argparse
from pathlib import Path

from run_route_grade_response import main as route_main


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__ or "Run a CINDER launch-tool scenario.")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--preset", type=Path, default=None)
    parser.add_argument("--report-step-s", type=float, default=0.05)
    parser.add_argument("--no-show", action="store_true")
    args, _unknown = parser.parse_known_args(argv)
    forwarded = []
    if args.output_dir is not None:
        forwarded += ["--output-dir", str(args.output_dir)]
    else:
        forwarded += ["--output-dir", str(Path("outputs") / Path(__file__).stem)]
    if args.preset is not None:
        forwarded += ["--preset", str(args.preset)]
    forwarded += ["--report-step-s", str(args.report_step_s)]
    if args.no_show:
        forwarded += ["--no-show"]
    route_main(forwarded)


if __name__ == "__main__":
    main()
