"""Cheap preflight for the CINDER 1.1.2 operating-domain invariant study."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
RELEASE_ROOT=HERE.parents[1]
if str(RELEASE_ROOT) not in sys.path:
    sys.path.insert(0,str(RELEASE_ROOT))

import cinder
from cinder.contracts import validate_simulation_case_document
from cinder.execution.hybrid.composed import ComposedCVTHybridSystem
from cinder.hosts import NoHost
from cinder.model.boundaries.shaft import FixedShaftBoundary
from cinder.model.cvt.contact import EngagedContactMode, SlipDirection, evaluate_contact_relative_speed
from cinder.results.fields import recover_belt_tension_boundaries
from cinder.results.inspection import inspect_cvt_state
from support.reference_model import decode_results_simulation_case_document, reference_model_status

subprocess.run([sys.executable,str(RELEASE_ROOT/"verify_environment.py")],check=True)
assert cinder.__version__=="1.1.2"
spec=json.loads((HERE/"study.json").read_text(encoding="utf-8"))
base=(HERE/spec["base_document"]).resolve(); assert base.is_file(),base
policy_path=(HERE/spec["reference_model_policy"]).resolve(); assert policy_path.is_file(),policy_path
case_library_path=(HERE/spec["shared_case_library"]).resolve(); assert case_library_path.is_file(),case_library_path
case_library=json.loads(case_library_path.read_text(encoding="utf-8"))
assert int(case_library.get("schema_version",0)) >= 3
assert set(case_library.get("targeted_contact_states",{})) == {"both_slip_mp","secondary_slip_plus"}
doc=json.loads(base.read_text(encoding="utf-8")); report=validate_simulation_case_document(doc); assert report.is_valid,report.findings
decoded=decode_results_simulation_case_document(doc)
assert reference_model_status(decoded.plant).secondary_helix_topology=="bilateral_zero_clearance_slot"
assert callable(inspect_cvt_state); assert callable(recover_belt_tension_boundaries); assert callable(evaluate_contact_relative_speed)
assert ComposedCVTHybridSystem is not None and NoHost is not None and FixedShaftBoundary is not None
assert {m.value for m in EngagedContactMode} == {"stick_stick","primary_slip_secondary_stick","primary_stick_secondary_slip","both_slip"}
assert SlipDirection.BELT_LEADS_PULLEY.value=="belt_leads_pulley"
standard=case_library["contact_search"]["standard"]
extended=case_library["contact_search"]["extended"]
boundaries=case_library["structural_boundary_cases"]
assert float(standard["minimum_branch_time_s"]) > 0.0
assert extended["shift_fractions"]
assert 0.0 in boundaries["lower_primary_speeds_rad_s"]
assert 0.0 in boundaries["lower_secondary_speeds_rad_s"]
required_ids={
    "stick_stick_forward","stick_stick_reverse","primary_slip_plus","primary_slip_minus",
    "secondary_slip_plus","secondary_slip_minus","both_slip_pp","both_slip_pm","both_slip_mp","both_slip_mm",
}
assert {item["id"] for item in case_library["contact_branch_requests"]} == required_ids
assert not any(key in spec for key in ("bench_search","extended_contact_search","static_rest","free_shift_cases","boundary_cases","classifier_controls")), "shared case recipes must not be duplicated in study.json"
assert {item["id"] for item in case_library["free_shift_direction_requests"]} == {"free_shift_closing","free_shift_opening"}
assert len(case_library["structural_boundary_requests"]) == 4
assert case_library["deadzone_free_snapshot"]["id"] == "deadzone_free_static_snapshot"
assert (HERE/"run_reference.py").is_file()
assert (HERE/"CAPABILITY_INTERPRETATION.md").is_file()
assert (HERE/"run_capability_probes.py").is_file()
print("PASS mechanical-invariants operating-domain preflight")
print(f"Shared cases: {case_library_path}")
print("Results secondary helix: bilateral_zero_clearance_slot")
