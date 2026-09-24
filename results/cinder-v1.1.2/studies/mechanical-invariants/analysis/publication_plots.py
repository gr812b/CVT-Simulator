"""Selected Section 4.2.1 evidence, checked before publication plotting.

No dynamics are run here. Dwell comes from the selected audit's exact event
records, never from a candidate-screening run. Local loading minima are taken
over the audited states, including each continuous segment's endpoints.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

from .execution_record import digest, verify_execution_record

CASE_LABELS = {
    "stick_stick_forward": "Stick–stick, forward",
    "stick_stick_reverse": "Stick–stick, reverse",
    "primary_slip_plus": "Primary slip (+)",
    "primary_slip_minus": "Primary slip (−)",
    "secondary_slip_plus": "Secondary slip (+)",
    "secondary_slip_minus": "Secondary slip (−)",
    "both_slip_pp": "Both slip (+,+)",
    "both_slip_pm": "Both slip (+,−)",
    "both_slip_mp": "Both slip (−,+)",
    "both_slip_mm": "Both slip (−,−)",
}
BOOLEAN_FIELDS = {
    "slip_direction_consistent", "mechanism_contacts_admissible",
    "successor_exists", "covered", "pass", "accepted", "finite_geometry",
    "positive_geometry",
}


def read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"Missing required evidence: {path.name}")
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for key in BOOLEAN_FIELDS & row.keys():
            if row[key] == "":
                row[key] = None
                continue
            if row[key] not in ("True", "False"):
                raise ValueError(f"Invalid boolean {key}: {row[key]!r}")
            row[key] = row[key] == "True"
    return rows


def minimum(rows: list[dict], key: str) -> float:
    values = [float(r[key]) for r in rows]
    if not values or not all(math.isfinite(v) for v in values):
        raise ValueError(f"Nonfinite/missing values for {key}")
    return min(values)


def first_exit(rows: list[dict], events: list[dict], window: float) -> dict:
    """Return the actual first exit or a verified finite observation bound."""
    if not rows or abs(float(rows[0]["time_s"])) > 1e-13:
        raise ValueError("Case does not begin at t=0.")
    if abs(float(rows[-1]["time_s"]) - window) > 1e-12:
        raise ValueError("Case does not cover the complete audit window.")
    ends = [r for r in rows if r["sample_location"] == "segment_end"]
    if not ends:
        raise ValueError("Missing native segment end.")
    if events:
        event = min(events, key=lambda r: float(r["time_s"]))
        dwell = float(event["time_s"])
        if not event["successor_exists"] or event.get("inspection_error"):
            raise ValueError("First transition has no inspected successor.")
        if abs(dwell - float(ends[0]["time_s"])) > 1e-12:
            raise ValueError("First event disagrees with the initial segment end.")
        return {"dwell_s": dwell, "lower_bound": False,
                "first_exit": event["fired_event_names"],
                "transition_reason": event["transition_reason"],
                "successor_contact": event["contact_mode"]}
    if len(ends) != 1:
        raise ValueError("Segment changes without event records.")
    return {"dwell_s": window, "lower_bound": True,
            "first_exit": "none within audit window", "transition_reason": "",
            "successor_contact": ""}


def collect_evidence(artifacts: Path, core) -> tuple[list[dict], dict, dict]:
    provenance = verify_execution_record(artifacts)
    summary = json.loads((artifacts / "summary.json").read_text())
    if summary["overall_status"] != "PASS" or summary["cinder_version"] != "1.1.2":
        raise ValueError("This publication selection requires a passing v1.1.2 audit.")
    samples = read_rows(artifacts / "sample_audit.csv")
    events = read_rows(artifacts / "post_transition_audit.csv")
    coverage = read_rows(artifacts / "coverage_matrix.csv")
    cases = {r["case_id"]: r for r in read_rows(artifacts / "case_summary.csv")}
    definitions = {r["case_id"]: r for r in read_rows(artifacts / "case_definitions.csv")}
    library = json.loads((artifacts / "resolved_shared_operating_cases.json").read_text())
    saved_spec = artifacts / "execution_inputs/results/cinder-v1.1.2/studies/mechanical-invariants/study.json"
    guards = json.loads(saved_spec.read_text())["review_guards"]
    if len(samples) != summary["audited_samples"] or len(events) != summary["transitions"]:
        raise ValueError("Summary counts disagree with the underlying audit.")
    if not coverage or not all(r["covered"] for r in coverage):
        raise ValueError("Incomplete required coverage.")
    failures = []
    for row in samples + events:
        if "successor_exists" in row and not row["successor_exists"]:
            failures.append((row["case_id"], "missing successor"))
        failures.extend((row["case_id"], f) for f in core.hard_row_failures(row, guards))
    if failures:
        raise ValueError(f"Underlying state/successor checks failed: {failures[:8]}")
    for name in ("negative_controls.csv", "classifier_controls.csv"):
        controls = read_rows(artifacts / name)
        if not controls or not all(r["pass"] for r in controls):
            raise ValueError(f"Control checks failed: {name}")
    if len(read_rows(artifacts / "geometry_domain_audit.csv")) != summary["geometry_points"]:
        raise ValueError("Geometry sample count mismatch.")

    selected = []
    window = float(library["contact_search"]["standard"]["contact_case_duration_s"])
    for case_id, label in CASE_LABELS.items():
        mine = [r for r in samples if r["case_id"] == case_id]
        transitions = [r for r in events if r["case_id"] == case_id]
        row = {"case_id": case_id, "label": label,
               **first_exit(mine, transitions, window),
               "targeted_initial_state": definitions[case_id]["search_stage"] == "targeted_seed",
               "screening_dwell_s": float(definitions[case_id]["requested_mode_dwell_s"])}
        engaged = [r for r in mine if r["engagement"] == "engaged"]
        row["audited_states"] = len(mine)
        row["engaged_states_for_local_minimum"] = len(engaged)
        row["deadzone_states_excluded_from_wrap_minimum"] = len(mine) - len(engaged)
        mapping = {
            "min_primary_local_normal_N_per_rad": "primary_min_dnormal_dtheta_N_per_rad",
            "min_secondary_local_normal_N_per_rad": "secondary_min_dnormal_dtheta_N_per_rad",
            "min_primary_normal_N": "normal_primary_N",
            "min_secondary_normal_N": "normal_secondary_N",
        }
        for destination, source in mapping.items():
            value = minimum(engaged, source)
            if not math.isclose(value, float(cases[case_id][destination]), rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError(f"Case summary mismatch: {case_id}/{destination}")
            if value <= 0:
                raise ValueError("Nonpositive normal loading: revise the log-axis design; never discard this value.")
            row[destination] = value
            at_minimum = min(engaged, key=lambda r: float(r[source]))
            row[destination + "_time_s"] = float(at_minimum["time_s"])
            row[destination + "_contact_mode"] = at_minimum["contact_mode"]
            row[destination + "_sample_location"] = at_minimum["sample_location"]
            if "local" in destination:
                interface = "primary" if "primary" in destination else "secondary"
                row[destination + "_matched_resultant_N"] = float(at_minimum[f"normal_{interface}_N"])
        selected.append(row)
    checks = {
        "audited_states": len(samples), "exact_successors": len(events),
        "required_coverage_classes": len(coverage),
        "hard_state_and_successor_failures_recomputed": len(failures),
        "geometry_samples": summary["geometry_points"],
        "row_scaled_closure_max": max(float(r["closure_max_scaled_residual"])
                                       for r in samples if r["engagement"] == "engaged"),
        "no_exit_cases": [r["case_id"] for r in selected if r["lower_bound"]],
        "targeted_cases": [r["case_id"] for r in selected if r["targeted_initial_state"]],
        "selection_count": len(selected),
    }
    return selected, checks, provenance


def make_figure(selected: list[dict], output: Path) -> None:
    style = {"font.family": "serif", "font.serif": ["STIXGeneral"],
             "mathtext.fontset": "stix", "font.size": 9,
             "axes.labelsize": 9, "xtick.labelsize": 8, "ytick.labelsize": 9,
             "pdf.fonttype": 42, "axes.spines.top": False, "axes.spines.right": False}
    with plt.rc_context(style):
        fig, (left, right) = plt.subplots(1, 2, figsize=(6.5, 3.25), sharey=True)
        fig.subplots_adjust(left=.245, right=.982, bottom=.20, top=.80, wspace=.28)
        blue, orange = "#245b82", "#ad4c24"
        for index, row in enumerate(selected):
            targeted = row["targeted_initial_state"]
            colour = orange if targeted else blue
            dwell_ms = 1e3 * row["dwell_s"]
            left.plot(dwell_ms, index, marker=">" if row["lower_bound"] else "o",
                      color=colour, markersize=5, linestyle="none", zorder=3)
            text = "≥30 ms" if row["lower_bound"] else (
                f"{dwell_ms*1000:.3g} μs" if dwell_ms < 1 else f"{dwell_ms:.3g} ms")
            left.annotate(text, (dwell_ms, index), xytext=(-6, 5),
                          textcoords="offset points", ha="right" if dwell_ms > 3 else "left",
                          va="bottom", fontsize=7.5, color=colour)
            for key, marker, fill in (("primary", "o", blue), ("secondary", "s", "white")):
                right.plot(row[f"min_{key}_local_normal_N_per_rad"], index,
                           marker=marker, mfc=fill, mec=blue, ms=4.7, ls="none", zorder=3)
        left.set_yticks(np.arange(len(selected)), list(CASE_LABELS.values()))
        left.set_ylim(len(selected)-.55, -.65)
        left.set_xscale("log"); left.set_xlim(.004, 80)
        left.set_xticks([.01, .1, 1, 10, 30], ["0.01", "0.1", "1", "10", "30"])
        left.set_xlabel("Initial-branch duration [ms]")
        left.axvline(30, color=".65", ls="--", lw=.8, zorder=0)
        left.set_title("(a) Contact persistence", loc="left", pad=28, fontsize=10)
        right.set_xscale("log"); right.set_xlim(.025, 250)
        right.set_xticks([.1, 1, 10, 100], ["0.1", "1", "10", "100"])
        right.set_xlabel("Least local normal load [N/rad]")
        right.set_title("(b) Full-wrap contact", loc="left", pad=28, fontsize=10)
        for ax in (left, right):
            ax.grid(axis="x", color=".88", lw=.5)
            ax.grid(axis="y", color=".92", lw=.5)
            ax.tick_params(axis="y", length=0)
            ax.set_axisbelow(True)
        left.legend(handles=[Line2D([], [], marker="o", color=orange, ls="none", ms=4,
                                    label="Targeted initial state")],
                    frameon=False, loc="lower left", bbox_to_anchor=(-.02, 1.01), fontsize=8)
        right.legend(handles=[Line2D([], [], marker="o", color=blue, ls="none", ms=4, label="Primary"),
                              Line2D([], [], marker="s", color=blue, mfc="white", ls="none", ms=4, label="Secondary")],
                     frameon=False, loc="lower left", bbox_to_anchor=(-.02, 1.01), ncol=2,
                     fontsize=8, handletextpad=.3, columnspacing=.7)
        fig.text(.245, .055, "Right-pointing markers: no exit within 30 ms. Both horizontal axes are logarithmic.",
                 fontsize=8)
        output.mkdir(parents=True, exist_ok=True)
        metadata = {"Creator": "CINDER mechanical-invariants publication_plots.py",
                    "CreationDate": None, "ModDate": None}
        fig.savefig(output / "contact_regimes.pdf", metadata=metadata)
        fig.savefig(output / "contact_regimes.png", dpi=200)
        plt.close(fig)


def main(artifacts: Path, output: Path, core) -> dict:
    selected, checks, provenance = collect_evidence(artifacts, core)
    make_figure(selected, output)
    with (output / "contact_regimes_values.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(selected[0]))
        writer.writeheader(); writer.writerows(selected)
    record = {
        "manuscript_label": "fig:verification_contact_regimes",
        "manuscript_asset": "docs/CVT_Module_Formulation/figures/results/verification/contact_regimes.pdf",
        "run_id": provenance["run_id"],
        "execution_record_sha256": digest(artifacts / "execution_provenance.json"),
        "mechanics_version": provenance["packages"]["cinder-cvt"],
        "mechanics_commit": provenance["mechanics_commit"],
        "plot_script": "analysis/publication_plots.py",
        "plot_script_sha256": digest(Path(__file__)),
        "size_inches": [6.5, 3.25],
        "transformations": {
            "case_subset": list(CASE_LABELS),
            "duration": "First native selected-audit transition; absent exit is a verified 30 ms lower bound.",
            "local_normal": "Minimum over engaged sample_audit.csv states from 0 to 30 ms, including every engaged segment endpoint and successor segment start; deadzone states have no full-wrap field and are excluded explicitly. Each spatial minimum is analytic under the reduced wrap law.",
            "targeted": "Actual accepted search_stage equals targeted_seed; no operating-frequency inference.",
            "normalization": "None; seconds converted to milliseconds. Dimensional logarithmic axes require strictly positive values and reject others.",
            "events": "No interpolation, smoothing or lines across resets. Local extrema can occur in later regimes and at different times.",
        },
        "checks": checks,
        "outputs": {name: digest(output / name) for name in
                    ("contact_regimes.pdf", "contact_regimes.png", "contact_regimes_values.csv")},
        "author_status": "ready_for_author_review_not_author_accepted",
    }
    (output / "contact_regimes_provenance.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(checks, indent=2))
    return record
