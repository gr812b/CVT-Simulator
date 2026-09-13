"""Build a draft operating-capability map from mechanical-invariant artifacts.

This is an interpretation aid, not another hard PASS/FAIL gate.  It preserves
raw evidence needed to decide which contact classes are broad/easy, merely
short-lived, or require targeted stress-state construction.  The final
manuscript labels should be based on the planned local-neighbourhood sweep, not
on arbitrary thresholds in this postprocessor.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"
CASE_LIBRARY = (HERE / "../../defaults/verification_operating_cases.json").resolve()

CONTACT_IDS = [
    "stick_stick_forward", "stick_stick_reverse",
    "primary_slip_plus", "primary_slip_minus",
    "secondary_slip_plus", "secondary_slip_minus",
    "both_slip_pp", "both_slip_pm", "both_slip_mp", "both_slip_mm",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def number(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def truth(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8"); return
    fields=[]; seen=set()
    for row in rows:
        for key in row:
            if key not in seen: seen.add(key); fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer=csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def main() -> int:
    if not ARTIFACTS.is_dir():
        raise SystemExit("Run run_reference.py first; artifacts/ does not exist.")
    library=json.loads(CASE_LIBRARY.read_text(encoding="utf-8"))
    cases={r["case_id"]:r for r in read_csv(ARTIFACTS/"case_summary.csv")}
    attempts=read_csv(ARTIFACTS/"candidate_search_log.csv")
    transitions=read_csv(ARTIFACTS/"post_transition_audit.csv")
    probes=read_csv(ARTIFACTS/"capability_probe_states.csv")
    targeted=set(library.get("targeted_contact_states",{}))

    rows=[]
    for cid in CONTACT_IDS:
        c=cases.get(cid,{})
        mine=[r for r in attempts if r.get("case_id")==cid]
        accepted=[r for r in mine if truth(r.get("accepted"))]
        chosen=accepted[0] if accepted else {}
        dwell=number(chosen.get("requested_mode_dwell_s"))
        exits=[r for r in transitions if r.get("case_id")==cid]
        first_exit=min(exits,key=lambda r:number(r.get("time_s"))) if exits else {}
        flags=[]
        if cid in targeted: flags.append("targeted_reproduction_anchor")
        if math.isfinite(dwell) and dwell < 1e-3: flags.append("sub_millisecond_initial_branch")
        if math.isfinite(dwell) and dwell < 1e-4: flags.append("tens_of_microseconds_initial_branch")
        # This is deliberately a diagnostic label, not the final scientific category.
        if cid in targeted:
            draft="targeted / rare"
        elif "sub_millisecond_initial_branch" in flags:
            draft="standardly reachable but transient"
        else:
            draft="standardly reachable"
        probe_hits=[p for p in probes if p.get("target")==cid]
        probe_status="|".join(p.get("status","") for p in probe_hits)
        rows.append({
            "case_id":cid,
            "case_status":c.get("status","missing"),
            "draft_capability_flag":draft,
            "diagnostic_flags":"|".join(flags),
            "slotted_capability_probe_status":probe_status,
            "logged_search_attempts":len(mine),
            "accepted_search_stage":chosen.get("search_stage",""),
            "requested_branch_dwell_s":dwell,
            "first_transition_event":first_exit.get("fired_event_names",""),
            "first_transition_reason":first_exit.get("transition_reason",""),
            "min_belt_tension_N":number(c.get("min_belt_tension_N")),
            "min_primary_local_normal_N_per_rad":number(c.get("min_primary_local_normal_N_per_rad")),
            "min_secondary_local_normal_N_per_rad":number(c.get("min_secondary_local_normal_N_per_rad")),
            "min_primary_normal_N":number(c.get("min_primary_normal_N")),
            "min_secondary_normal_N":number(c.get("min_secondary_normal_N")),
            "max_scaled_closure_residual":number(c.get("max_scaled_closure_residual")),
        })

    write_csv(ARTIFACTS/"capability_map_draft.csv",rows)
    lines=[
        "# Draft contact-domain capability map", "",
        "This file is an interpretation aid generated from the invariant artifacts. "
        "The labels below are deliberately provisional; the planned local-neighbourhood sweep should be used before publishing broad/easy/constrained/extreme language.", "",
        "| Contact class | Draft flag | Initial branch dwell | First exit |", "|---|---|---:|---|",
    ]
    for r in rows:
        dwell=r["requested_branch_dwell_s"]
        dwell_text=f"{dwell:.6g} s" if math.isfinite(dwell) else "—"
        exit_text=(r["first_transition_event"] or r["first_transition_reason"] or "—").replace("|","/")
        lines.append(f"| `{r['case_id']}` | {r['draft_capability_flag']} | {dwell_text} | {exit_text} |")
    lines += ["", "## Next refinement", "",
        "For a publication-quality capability claim, perturb each canonical operating point over a common local neighbourhood and report separately: (1) forced requested-branch physical admissibility, (2) production-classifier retention of the requested topology, (3) branch dwell / exit event, and (4) the first violated physical inequality. The slotted results reference topology keeps secondary helix flank selection out of that belt-domain map."]
    (ARTIFACTS/"capability_map_draft.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("Wrote capability_map_draft.csv and capability_map_draft.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
