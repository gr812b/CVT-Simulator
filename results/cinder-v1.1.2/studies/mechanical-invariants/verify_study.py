"""Cheap preflight for the CINDER 1.1.2 operating-domain invariant study."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys

import cinder
from cinder.contracts import validate_simulation_case_document
from cinder.execution.hybrid.composed import ComposedCVTHybridSystem
from cinder.hosts import NoHost
from cinder.model.boundaries.shaft import FixedShaftBoundary
from cinder.model.cvt.contact import EngagedContactMode, SlipDirection, evaluate_contact_relative_speed
from cinder.results.fields import recover_belt_tension_boundaries
from cinder.results.inspection import inspect_cvt_state

HERE=Path(__file__).resolve().parent
RELEASE_ROOT=HERE.parents[1]
subprocess.run([sys.executable,str(RELEASE_ROOT/"verify_environment.py")],check=True)
assert cinder.__version__=="1.1.2"
spec=json.loads((HERE/"study.json").read_text(encoding="utf-8"))
base=(HERE/spec["base_document"]).resolve(); assert base.is_file(),base
doc=json.loads(base.read_text(encoding="utf-8")); report=validate_simulation_case_document(doc); assert report.is_valid,report.findings
assert callable(inspect_cvt_state); assert callable(recover_belt_tension_boundaries); assert callable(evaluate_contact_relative_speed)
assert ComposedCVTHybridSystem is not None and NoHost is not None and FixedShaftBoundary is not None
assert {m.value for m in EngagedContactMode} == {"stick_stick","primary_slip_secondary_stick","primary_stick_secondary_slip","both_slip"}
assert SlipDirection.BELT_LEADS_PULLEY.value=="belt_leads_pulley"
assert float(spec["bench_search"]["minimum_branch_time_s"]) > 0.0
assert "extended_contact_search" in spec
assert 0.0 in spec["boundary_cases"]["lower_primary_speeds_rad_s"]
assert 0.0 in spec["boundary_cases"]["lower_secondary_speeds_rad_s"]
print("PASS mechanical-invariants operating-domain preflight")
