"""Run discovery and stored evidence; these operations never execute CINDER."""

import csv
import io
import json
from copy import deepcopy

from pydantic import TypeAdapter
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import defer

from app.application import (
    access,
    configuration_copies,
    experiments,
    jobs,
    physical_library,
)
from app.application.physical_contracts import (
    baseline_case,
    belt_from_assembly,
    vehicle_boundary,
    vehicle_from_boundary,
)
from app.application.roads import apply_scenario
from app.core.errors import ApiProblem
from app.database import runs as artifacts
from app.database.models import Run, RunArtifact, RunCacheEntry
from app.database.publication_models import ConfigurationCopy
from app.schemas.experiments import PrimaryOverride, ScenarioDocument
from app.schemas.physical_library import SetupDocument
from app.schemas.results import (
    ResultAvailability,
    RunHistoryItem,
    RunHistoryPage,
    RunInspection,
    RunReference,
    RunSeries,
    RunSummaryExport,
)

METRICS = {
    "duration_s": ("Simulated duration", "s"),
    "vehicle_speed_max_m_per_s": ("Maximum vehicle speed", "m/s"),
    "vehicle_distance_final_m": ("Final road distance", "m"),
    "first_engagement_time_s": ("First engagement", "s"),
    "ratio_final": ("Final CVT ratio", ""),
    "transition_count": ("Transitions", ""),
    "primary_angular_speed_max_rad_per_s": ("Maximum primary speed", "rad/s"),
    "secondary_angular_speed_max_rad_per_s": ("Maximum secondary speed", "rad/s"),
    "primary_slip_duration_s": ("Primary slip duration", "s"),
    "secondary_slip_duration_s": ("Secondary slip duration", "s"),
    "ratio_min": ("Minimum CVT ratio", ""),
    "ratio_max": ("Maximum CVT ratio", ""),
    "primary_traction_utilization_max": ("Maximum primary traction utilization", ""),
    "secondary_traction_utilization_max": (
        "Maximum secondary traction utilization",
        "",
    ),
    "primary_boundary_work_final_J": ("Primary boundary work", "J"),
    "secondary_boundary_work_final_J": ("Secondary boundary work", "J"),
    "primary_slip_dissipation_final_J": ("Primary slip dissipation", "J"),
    "secondary_slip_dissipation_final_J": ("Secondary slip dissipation", "J"),
}


def references(run):
    p = run.provenance or {}
    tune = p.get("tune_document") or {}
    scenario = p.get("scenario") or run.load_case_snapshot or {}
    return [
        RunReference(
            kind=kind,
            name=name,
            revision_id=revision,
            revision_number=p.get(f"{kind}_revision_number"),
            unsaved=unsaved,
        )
        for kind, name, revision, unsaved in (
            (
                "setup",
                p.get("setup_name") or "Vehicle setup",
                p.get("setup_revision_id") or run.vehicle_assembly_version_id,
                False,
            ),
            (
                "tune",
                tune.get("name") or "Run values",
                p.get("tune_revision_id"),
                bool(p.get("tune_unsaved")),
            ),
            (
                "scenario",
                scenario.get("name") or "Load case",
                p.get("scenario_revision_id"),
                bool(p.get("scenario_unsaved")),
            ),
        )
    ]


def metric_values(run):
    values = (run.summary_scalars or {}).get("metrics", {})
    return [
        {"key": key, "label": label, "unit": unit, "value": values[key]}
        for key, (label, unit) in METRICS.items()
        if key in values
    ]


def history_item(run):
    return RunHistoryItem(
        run=jobs.status(run, include_provenance=False).model_copy(
            update={"summary_scalars": {}}
        ),
        references=references(run),
        metrics=metric_values(run)[:6],
    )


def history(
    session,
    principal,
    settings,
    *,
    query="",
    status=None,
    source=None,
    since=None,
    until=None,
    limit=24,
    offset=0,
    oldest_first=False,
    scope="own",
):
    if since and until and since > until:
        raise ApiProblem(
            422, "date_range", "The start date must be before the end date."
        )
    if principal.account_id:
        jobs.recover(session, settings, principal.account_id)
    conditions = [Run.account_id == principal.account_id] if scope == "own" else []
    if query.strip():
        escaped = (
            query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        columns = (
            Run.name,
            Run.id,
            Run.provenance["setup_name"].as_string(),
            Run.provenance["tune_document"]["name"].as_string(),
            Run.provenance["scenario"]["name"].as_string(),
        )
        conditions.append(
            or_(*[column.ilike(f"%{escaped}%", escape="\\") for column in columns])
        )
    if status:
        conditions.append(Run.status == status)
    if source:
        conditions.append(Run.source == source)
    if since:
        conditions.append(Run.submitted_at >= since)
    if until:
        conditions.append(Run.submitted_at <= until)
    total = session.scalar(select(func.count()).select_from(Run).where(*conditions))
    ordering = (
        (Run.submitted_at.asc(), Run.id.asc())
        if oldest_first
        else (Run.submitted_at.desc(), Run.id.desc())
    )
    rows = session.scalars(
        select(Run)
        .options(defer(Run.input_contract), defer(Run.summary_series))
        .where(*conditions)
        .order_by(*ordering)
        .offset(offset)
        .limit(limit)
    )
    return RunHistoryPage(
        items=[history_item(run) for run in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


def availability(session, run):
    # Read availability/hash without transferring full JSON payloads from the DB.
    full = session.execute(
        select(
            RunArtifact.id,
            RunArtifact.content_hash,
            RunArtifact.inline_payload.is_not(None),
        ).where(
            RunArtifact.run_id == run.id,
            RunArtifact.artifact_kind == "full_result",
        )
    ).first()
    if full is None and run.cache_entry_id:
        full = session.execute(
            select(
                RunArtifact.id,
                RunArtifact.content_hash,
                RunArtifact.inline_payload.is_not(None),
            )
            .join(
                RunCacheEntry,
                RunCacheEntry.full_result_artifact_id == RunArtifact.id,
            )
            .where(RunCacheEntry.id == run.cache_entry_id)
        ).first()
    preview = bool(run.summary_series) or bool(
        session.scalar(
            select(RunArtifact.id)
            .where(
                or_(
                    RunArtifact.run_id == run.id,
                    (RunArtifact.cache_entry_id == run.cache_entry_id)
                    & (RunArtifact.cache_entry_id.is_not(None)),
                ),
                RunArtifact.artifact_kind == "preview_series",
                RunArtifact.inline_payload.is_not(None),
            )
            .limit(1)
        )
    )
    metrics = (run.summary_scalars or {}).get("metrics", {})
    return ResultAvailability(
        full_result=bool(full and full[2]),
        full_result_hash=full[1] if full else None,
        preview=preview,
        partial=metrics.get("completed") is False,
        original_row_count=(run.summary_series or {}).get("original_row_count"),
    )


def _experiment_configuration(run, settings):
    """Only offer an editable copy when the editor reproduces all executable fields."""
    case = run.input_contract
    p = run.provenance or {}
    if (run.execution_options or {}).get("execution_profile", "default") != "default":
        raise ValueError(
            "This run uses a specialized execution profile. Use its original workspace or rerun the frozen input."
        )
    if (
        not isinstance(p.get("scenario"), dict)
        or p["scenario"].get("kind") != "scenarios"
    ):
        raise ValueError(
            "This older or specialized run has no editable scenario definition. Its canonical input can still be exported or rerun."
        )
    scenario = ScenarioDocument.model_validate(p["scenario"])
    primary = case["shaft_boundaries"]["primary"]
    override = None
    if primary["kind"] != "full_throttle_engine":
        override = TypeAdapter(PrimaryOverride).validate_python(
            p.get("primary_boundary")
        )
    engine = baseline_case()["shaft_boundaries"]["primary"] if override else primary
    document = SetupDocument.model_validate(
        {
            "kind": "setups",
            "name": f"{run.name[:210]} setup",
            "source_label": f"Simulation {run.id}",
            "data": {
                "engine": {
                    "name": "Baseline engine (inactive)"
                    if override
                    else "Engine from run",
                    "data": engine,
                },
                "cvt": {
                    "name": "CVT from run",
                    "data": {
                        "assembly": deepcopy(case["assembly"]),
                        "belt": {
                            "name": "Belt from run",
                            "data": belt_from_assembly(case["assembly"]).model_dump(),
                        },
                    },
                },
                "vehicle": vehicle_from_boundary(
                    case["shaft_boundaries"]["secondary"]
                ).model_dump(),
            },
        }
    )
    candidate = baseline_case()
    candidate["assembly"] = document.data.cvt.data.assembly
    candidate["shaft_boundaries"] = {
        "primary": override.model_dump()
        if override
        else document.data.engine.data.model_dump(),
        "secondary": vehicle_boundary(document.data.vehicle),
    }
    apply_scenario(candidate, scenario, settings)
    if any(
        candidate[key] != case[key]
        for key in ("assembly", "shaft_boundaries", "host", "scenario", "execution")
    ):
        raise ValueError(
            "This run contains settings outside the current experiment editor. Export or rerun its exact frozen input."
        )
    return document, scenario


def copy_unavailable_reason(run, settings):
    try:
        _experiment_configuration(run, settings)
    except (ValueError, KeyError, TypeError, ApiProblem) as exc:
        return (
            str(exc)
            if isinstance(exc, ValueError) and len(str(exc)) < 500
            else "The frozen configuration cannot be represented by the current experiment editor. Export or rerun its exact input."
        )
    return None


def inspect_run(session, principal, settings, run_id):
    run = access.public_run(session, run_id)
    if principal.account_id == run.account_id:
        jobs.recover(session, settings, principal.account_id)
    summary = run.summary_scalars or {}
    return RunInspection(
        run=jobs.status(run),
        references=references(run),
        metrics=metric_values(run),
        availability=availability(session, run),
        warnings=[
            value if isinstance(value, str) else json.dumps(value)
            for value in summary.get("warnings", [])
        ],
        transitions=[
            {
                "time_s": value["time_s"],
                "events": value.get("fired_event_names", []),
                "reason": value.get("reason", ""),
                "terminates": value.get("terminates", False),
            }
            for value in summary.get("transitions", [])
        ],
        termination_reason=summary.get("metrics", {}).get("termination_reason"),
        experiment_copy_unavailable_reason=copy_unavailable_reason(run, settings),
    )


def series(session, principal, run_id, resolution):
    run = access.public_run(session, run_id)
    table = (
        artifacts.get_database_run_result(session, run.id)["report_table"]
        if resolution == "full"
        else artifacts.get_database_run_preview(session, run.id)
    )
    return RunSeries(
        resolution=resolution,
        axis_key=table.get("axis_key") or "time_s",
        original_row_count=table.get("original_row_count", table.get("row_count", 0)),
        row_count=table.get("preview_row_count", table.get("row_count", 0)),
        columns=[
            {
                key: column.get(key, "")
                for key in (
                    "key",
                    "label",
                    "canonical_unit",
                    "dimension",
                    "group",
                    "description",
                    "values",
                )
            }
            for column in table.get("columns", [])
        ],
    )


def rename(session, principal, run_id, request):
    run = access.owned(session.get(Run, run_id), principal, write=True)
    if not request.name.strip():
        raise ApiProblem(422, "run_name", "Enter a name for this run.")
    if not session.execute(
        update(Run)
        .where(Run.id == run.id, Run.name == request.expected_name)
        .values(name=request.name.strip())
        .execution_options(synchronize_session=False)
    ).rowcount:
        raise ApiProblem(
            409,
            "run_name_conflict",
            "The name changed in another tab. Reload before renaming.",
        )
    session.refresh(run)
    return jobs.status(run)


def export(session, principal, run_id, kind):
    run = access.public_run(session, run_id)
    if kind == "input":
        payload = run.input_contract
    elif kind == "summary":
        payload = RunSummaryExport(
            run=jobs.status(run),
            references=references(run),
            availability=availability(session, run),
            summary=run.summary_scalars or {},
        ).model_dump(mode="json")
    else:
        payload = artifacts.get_database_run_result(session, run.id)
    if kind == "csv":
        table = payload["report_table"]
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(
            [
                f"{column['key']} [{column['canonical_unit']}]"
                for column in table["columns"]
            ]
        )
        writer.writerows(
            [
                [
                    column["values"][index] if index < len(column["values"]) else None
                    for column in table["columns"]
                ]
                for index in range(table["row_count"])
            ]
        )
        return stream.getvalue(), "text/csv", "csv"
    return (
        json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2),
        "application/json",
        "json",
    )


def copy_experiment(session, principal, settings, run_id, request):
    run = access.public_run(session, run_id)
    existing, fingerprint = configuration_copies.begin_copy(
        session, principal, request, {"run": run.id}
    )
    if existing:
        return configuration_copies.copy_result(session, principal, existing)
    reason = copy_unavailable_reason(run, settings)
    if reason:
        raise ApiProblem(422, "experiment_copy_unavailable", reason)
    document, scenario = _experiment_configuration(run, settings)
    document.name = request.name or document.name
    obj, _ = physical_library.save_document(
        session,
        principal,
        document,
        duplicate=True,
        note=f"Frozen physical values from run {run.id}; includes its tune and mass override.",
    )
    scenario_obj, _ = experiments.save(
        session,
        principal,
        settings,
        scenario,
        note=f"Copied the frozen scenario from run {run.id}.",
    )
    record = ConfigurationCopy(
        account_id=principal.account_id,
        request_key=request.request_key,
        request_hash=fingerprint,
        kind="setups",
        object_id=obj.id,
        run_id=run.id,
        scenario_id=scenario_obj.id,
    )
    session.add(record)
    session.flush()
    return configuration_copies.copy_result(session, principal, record)
