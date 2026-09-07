# CINDER source layout and dependency boundaries

CINDER keeps the mechanical model, execution machinery, post-integration
results, and JSON/document boundary separate.  The intended dependency
direction is:

```text
model / hosts
     ↓
execution
     ↓
results
     ↓
contracts
```

`studies` is a parallel public analysis surface for calculations that do not
require time integration.

## `src/cinder`

```text
src/cinder/
├─ core/          generic state-layout utilities
├─ model/         physical CVT model and shaft-boundary definitions
├─ execution/     hybrid regimes, events, integration, and runtime closure
├─ hosts/         external host-state adapters used by composed simulations
├─ results/       post-integration inspection, reporting, and derived fields
├─ contracts/     stable JSON-safe documents and result projection
└─ studies/       supported static geometry/actuation studies
```

### `model`

Owns the physical formulation: geometry, actuation, contact laws, inertias,
closure equations, and the five-state mechanical plant.  It must not depend on
HTTP, JSON documents, plotting, or frontend concerns.

### `execution`

Owns time advancement and hybrid mechanics: operating regimes, event detection,
state/reset transitions, contact switching, and integration.  The runtime
result remains deliberately lean; plot-ready or spatial outputs do not belong
in the integration state or RHS.

### `results`

Owns reconstruction from an already integrated trace.  This is where CINDER
turns stored states into user-facing quantities without rerunning the solve.

Current result responsibilities are:

```text
results/inspection.py     rich one-state mechanical inspection
results/reporting.py      time-aligned NumericSignal report construction
results/fields/           reusable spatial domains and derived fields
results/trace.py           raw accepted solver trace and transitions
```

`results/fields` contains two deliberately separate ideas:

- **generic field infrastructure** (`expression.py`, `types.py`) — a small
  JSON-safe mathematical expression language plus domain/field/sample types;
- **physical field definitions** (`belt.py`) — CINDER-owned definitions such as
  `belt.path` and `belt.tension` built from ordinary report signals.

The generic expression evaluator knows only literals, a local coordinate,
named report signals, and ordinary mathematical operators.  It contains no
belt- or CVT-specific branches.  This lets the same compact field definition be
materialized in Python or passed through an API to another generic evaluator.

### `contracts`

Owns the stable external/document boundary.  Core mechanics do not import this
layer.  `project_simulation_result()` projects the same `CVTIntegrationResult`
used by Python callers into a JSON-safe payload for an HTTP backend or saved
artifact.

A simulation result now exposes three complementary result forms under the
same public contract version:

```text
report_table    scalar time histories

domains         reusable spatial geometry definitions
fields          scalar fields defined over those domains
```

There is no separately versioned spatial contract.  Domains and fields are
part of the normal simulation-result projection and reference report-table
signals by their stable keys.

## Solver / result-field boundary

Derived fields must not add ODE states, alter closure unknowns, or execute
inside the adaptive solver RHS.  The intended flow is:

```text
solver / hybrid execution
        ↓
CVTIntegrationTrace
        ↓
CVTResultBuilder
        ├─ ordinary NumericSignal columns
        └─ compact field/domain definitions
        ↓
CVTIntegrationResult
        ├─ result.field("belt.tension").sample(...)
        └─ project_simulation_result(...)
```

For the present analytical belt-tension field, the reporting pass adds only the
four wrap-boundary tensions per report frame.  The continuous field definition
is stored once and references those signals together with existing geometry and
traction-utilization signals.

## Adding another spatial field

A new analytical field should normally require only:

1. expose any genuinely useful new scalar boundary/coefficient quantities as
   normal report signals;
2. define the field in `results/fields/` using the generic expression nodes;
3. register the field when `CVTResultBuilder` constructs the result;
4. add public metadata/documentation as needed.

No frontend-specific equation and no solver modification should be required.
