# Getting started with CINDER's public contract

CINDER has two complementary APIs:

1. **Python mechanics APIs** under `cinder.model`, `cinder.execution`, and `cinder.studies` for researchers and package developers.
2. **Public-contract APIs** under `cinder.contracts` for saved designs, backends, generated client types, and generic user interfaces.

The public contract uses canonical SI values. It does not require a frontend to
recreate pulley geometry, belt closure, actuator equations, output-boundary
loads, or solver configuration.

## Install in development mode

From the `cvtModel` repository root:

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

python -m pip install -e ".[dev]"
```

CINDER itself is imported as `cinder`. Root-level `launchTools` remains project
instrumentation and is not part of CINDER's public package contract.

## Start from a full simulation document

`examples/baja_baseline_simulation_case.json` includes:

```text
assembly
input boundary / engine torque curve
output boundary / locked final-drive vehicle
scenario / initial state
execution / traction, solver, integration, and reporting settings
```

Load and validate it before building a runtime:

```python
import json
from pathlib import Path

from cinder.contracts import (
    decode_simulation_case_document,
    validate_simulation_case_document,
)

path = Path("examples/baja_baseline_simulation_case.json")
document = json.loads(path.read_text())

validation = validate_simulation_case_document(document)
for finding in validation.findings:
    print(finding.severity, finding.document_path, finding.message)
if not validation.is_valid:
    raise RuntimeError("Fix document errors before running.")

decoded = decode_simulation_case_document(document)
```

`decoded` is a small immutable bundle of ordinary CINDER objects:

```python
case = decoded.case
config = decoded.operating_system_config
integrator_settings = decoded.integrator_settings
reporting_settings = decoded.reporting_settings
```

The decoder does not create a second mechanics model. `case` is the normal
`CVTSimulationCase` used by direct Python callers.

## Run the document

```python
system = decoded.build_system()
scenario = decoded.case.scenario

result = system.run(
    time_span=scenario.time_span,
    initial_state=scenario.initial_state,
    initial_regime=scenario.initial_mode,
    settings=decoded.integrator_settings,
    reporting_settings=decoded.reporting_settings,
)
```

The default document uses a uniform report grid. The adaptive raw trace remains
on `result.trace`; it is not lost when report data is materialized.

## Project a JSON-safe result

```python
from cinder.contracts import project_simulation_result

payload = project_simulation_result(result)
report_table = payload["report_table"]

print(report_table["axis_key"])      # time_s
print(report_table["columns"][0])    # descriptor + values
print(payload["transitions"])        # exact hybrid transition markers
```

`report_table` has a shared time axis and named self-describing columns. A
transition that projects the state is represented by duplicate timestamps, not
by interpolating through the discontinuity. The frontend may plot this directly.

For detailed hybrid inspection, request only the extra data you need:

```python
payload = project_simulation_result(
    result,
    include_reported_segments=True,  # uniform report split by hybrid segment
    include_raw_trace=True,          # accepted adaptive solver mesh
)
reported_segments = payload["reported_segments"]
raw_trace = payload["raw_trace"]
```

Those payloads are intentionally opt-in. Normal charts, playback, and 3D views
should use the single default `report_table`.

## Discover editable fields instead of maintaining parameter maps

```python
from cinder.contracts import editable_simulation_case_schema

schema = editable_simulation_case_schema()
for field in schema["fields"]:
    print(field["path_template"], field["canonical_unit"])
```

Each descriptor names a document path, type, canonical unit, physical
dimension, exposure level, bounds when known, and an optional discriminator
condition. `design` fields describe CVT hardware, `scenario` fields describe a
run's boundaries and initial state, and `advanced_execution` fields describe
numerical/reporting controls. Repeated
items use `*` in `path_template`; for example:

```text
/input_boundary/points/*/torque_Nm
/assembly/pulleys/input/components/*/kind
```

The schema is factual. It does not prescribe UI layout or recommend tuning.

## Units

Documents, CINDER calculations, API payloads, and 3D geometry all use
canonical SI values. A frontend display profile may show `mm`, `rpm`, or `deg`,
but it should use `dimension` and `canonical_unit` from CINDER's descriptors.
It should not maintain a CVT-specific conversion map keyed by nested property
names.

## Runnable walkthrough

```bash
python examples/quickstart.py
python examples/quickstart.py --run
```

The first command validates and decodes the document. The second performs the
full baseline run and prints flattened report-table fields.
