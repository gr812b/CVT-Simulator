# Backend / frontend handoff after Phase 1

## Backend call path

The backend should stay thin:

```python
decoded = decode_simulation_case_document(request.document)
validation = validate_simulation_case_document(request.document)

if not validation.is_valid:
    return validation.as_dict()

system = decoded.build_system()
result = system.run(
    time_span=decoded.case.scenario.time_span,
    initial_state=decoded.case.scenario.initial_state,
    initial_regime=decoded.case.scenario.initial_mode,
    settings=decoded.integrator_settings,
    reporting_settings=decoded.reporting_settings,
)
return project_simulation_result(result)
```

The backend does not rebuild pulley objects or interpret a flat parameter
override map. It accepts a versioned document and returns a CINDER projection.

## Metadata endpoints

The first backend endpoints can directly wrap these functions:

```text
GET  /metadata/conventions       -> public_conventions().as_dict()
GET  /metadata/components        -> component_catalog_document()
GET  /metadata/editable-schema   -> editable_simulation_case_schema()
POST /designs/validate           -> validate_simulation_case_document(document)
POST /runs                        -> decode -> run -> project
```

Static study endpoints can use the existing CINDER geometry and actuation
study contracts. Do not call them generic `/solvers`; route names should
represent engineering questions.

## Frontend rules

Store one canonical `SimulationCaseDocument` draft. Do not split it into a
parallel `ParameterState` with field aliases. Patch document paths directly.

Use field `dimension` and `canonical_unit` for a generic display-unit editor.
The conversion layer may understand physical units such as metres and RPM, but
it must not know CVT-specific paths or derive any missing mechanical values.

Render charts from `report_table.columns` plus `transitions`. A backend view
manifest can later decide which signal groups/panels appear on a route, but the
frontend should not reconstruct a signal from other output fields.

For 3D animation, read CINDER-projected geometry signal columns. Frontend math
is limited to scene-coordinate calibration and metres-to-render-scale mapping.
