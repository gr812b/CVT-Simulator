"""Summarize retained starting-guess outcomes without reevaluating mechanics.

This reads the same full-run CSV used by canonical run.py --plot-only. It
distinguishes successful optimizer termination from sticking compatibility;
the historical rows do not retain individual optimizer termination messages.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def summarize(artifacts: Path) -> dict:
    path = artifacts / "full/multistart_results.csv"
    with path.open() as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 735 or len({r["state"] for r in rows}) != 15:
        raise ValueError("Expected the complete 15-state, 735-start census.")
    good = [r for r in rows if r["accepted"] == "True"]
    bad = [r for r in rows if r["accepted"] == "False"]
    if len(good) + len(bad) != len(rows):
        raise ValueError("Unknown acceptance flag.")
    bound = [r for r in bad if abs(abs(float(r["root_lambda_s"])) - 1.95) < 1e-8]
    per_state = []
    for state in dict.fromkeys(r["state"] for r in rows):
        selected = [r for r in rows if r["state"] == state]
        accepted = [r for r in selected if r["accepted"] == "True"]
        if len(selected) != 49:
            raise ValueError(f"Incomplete starting grid: {state}")
        per_state.append({"state": state, "starts": len(selected),
                          "accepted": len(accepted),
                          "not_accepted": len(selected) - len(accepted)})
    result = {
        "input": "full/multistart_results.csv",
        "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "total": len(rows), "accepted": len(good), "rejected": len(bad),
        "rejected_with_optimizer_success": sum(r["optimizer_success"] == "True" for r in bad),
        "rejected_with_static_admissibility_false": sum(r["statically_admissible"] == "False" for r in bad),
        "rejected_secondary_outside_static_limit": sum(abs(float(r["root_lambda_s"])) > .65 for r in bad),
        "rejected_residual_norm_m_s2": [min(float(r["residual_norm"]) for r in bad),
                                       max(float(r["residual_norm"]) for r in bad)],
        "accepted_max_residual_norm_m_s2": max(float(r["residual_norm"]) for r in good),
        "rejected_secondary_at_numeric_bound_within_1e_8": len(bound),
        "rejected_secondary_inside_numeric_bounds": len(bad) - len(bound),
        "per_state": per_state,
        "new_mechanical_evaluations": 0,
        "limit": "Stored residuals establish failure to reach sticking; exact optimizer termination reasons were not retained.",
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    data = summarize(args.artifacts_dir)
    data["summary_script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2) + "\n")
    print(f"{data['accepted']} accepted; {data['rejected']} rejected; no mechanical evaluations.")


if __name__ == "__main__":
    main()
