"""Four-case numerical-refinement audit for the Ballew closed-loop benchmark."""

from __future__ import annotations

# --- results study-local import bootstrap ---
from pathlib import Path as _ResultsPath
import sys as _results_sys

_results_file = _ResultsPath(__file__).resolve()
_results_study_root = next(
    (parent for parent in _results_file.parents if (parent / "study.json").is_file()),
    None,
)
if _results_study_root is None:
    raise RuntimeError(f"Could not locate study root for {_results_file}")
_results_release_root = _results_study_root.parents[1]
for _results_path in (str(_results_study_root), str(_results_release_root)):
    while _results_path in _results_sys.path:
        _results_sys.path.remove(_results_path)
_results_sys.path.insert(0, str(_results_release_root))
_results_sys.path.insert(0, str(_results_study_root))
# --- end results study-local import bootstrap ---


import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys

import cinder

from run import _run_protocol
from infrastructure.benchmark.reference import validate_reference_data

STUDY_ROOT = Path(__file__).resolve().parents[1]
RELEASE_ROOT = STUDY_ROOT.parents[1]
OUTPUT = STUDY_ROOT / "artifacts" / "convergence"
CASES = (
    ("nominal_1p00ms", 1.0e-7, 1.0e-9, 1.0e-3),
    ("nominal_0p50ms", 1.0e-7, 1.0e-9, 0.5e-3),
    ("nominal_0p25ms", 1.0e-7, 1.0e-9, 0.25e-3),
    ("tight_0p50ms", 3.0e-8, 3.0e-10, 0.5e-3),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-nominal", action="store_true",
                        help="reuse the verified canonical closed-loop 1 ms result")
    args = parser.parse_args()
    subprocess.run([sys.executable, str(RELEASE_ROOT / "verify_environment.py")], check=True)
    subprocess.run([sys.executable, str(STUDY_ROOT / "verify_study.py")], check=True)
    if cinder.__version__ != "1.1.2":
        raise RuntimeError("The refinement requires cinder-cvt==1.1.2")
    spec = json.loads((STUDY_ROOT / "study.json").read_text())
    reference = validate_reference_data(study_root=STUDY_ROOT)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for label, rtol, atol, cap in CASES:
        directory = OUTPUT / label
        if label == "nominal_1p00ms" and args.reuse_nominal:
            directory = STUDY_ROOT / "artifacts/closed-loop"
            payload = json.loads((directory / "metrics.json").read_text())
            solver = payload["solver"]
            assert (solver["relative_tolerance"], solver["absolute_tolerance"],
                    solver["max_step_s"]) == (rtol, atol, cap)
            record = json.loads((directory / "execution_provenance.json").read_text())
            assert record["cinder_version"] == "1.1.2"
            import hashlib
            for name, digest in record["output_sha256"].items():
                assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
        else:
            print(f"Running {label}...", flush=True)
            override = argparse.Namespace(rtol=rtol, atol=atol, max_step=cap,
                                          maximum_transitions=2000)
            payload = _run_protocol(protocol="closed_loop", spec=spec,
                                    reference_dir=reference, make_plots=False,
                                    args=override, output_dir=directory)
        row = dict(label=label, rtol=rtol, atol=atol, max_step_s=cap,
                   completed=payload["completed"],
                   termination_reason=payload["termination_reason"],
                   transition_count=payload["transition_count"],
                   segment_count=payload["segment_count"],
                   artifact_path=str(directory.relative_to(STUDY_ROOT / "artifacts")))
        for key, metric in payload.get("metrics", {}).items():
            row[key + "_rmse"] = metric["root_mean_square_error"]
        rows.append(row)
        (OUTPUT / "convergence.json").write_text(json.dumps(
            {"cinder_version": cinder.__version__, "cases": rows}, indent=2) + "\n")
        with (OUTPUT / "convergence.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader();w.writerows(rows)
        print(f"{label}: completed={row['completed']}; transitions={row['transition_count']}", flush=True)
    return 0 if all(r["completed"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
