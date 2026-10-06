"""Run discovery and stored evidence; these operations never execute CINDER."""

import csv
import io
import json

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import defer

from app.application import (
    access,
    experiments,
    jobs,
    physical_library,
    run_outcomes,
)
from app.application.experiment_tuning import tune_surface
from app.core.errors import ApiProblem
from app.database import library
from app.database import runs as artifacts
from app.database.models import Run, RunArtifact, RunCacheEntry
from app.schemas.experiments import ExperimentSelection
from app.schemas.results import (
    ResultAvailability,
    RunExperimentDraft,
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


def references(run, session=None, principal=None):
    p = run.provenance or {}
    tune = p.get("tune_document") or {}
    scenario = p.get("scenario") or run.load_case_snapshot or {}
    result = [
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

    if session is None:
        return result
    # Link the exact saved revisions, including components resolved by the setup.
    setup_id = p.get("setup_revision_id") or run.vehicle_assembly_version_id
    setup = None
    if setup_id:
        try:
            setup = access.library_version(session, principal, "vehicle-assemblies", setup_id)
        except ApiProblem:
            pass
    component_versions = {
        "cvt": (
            "cvt-designs",
            "cvts",
            p.get("cvt_revision_id") or (setup.cvt_design_version_id if setup else None),
        ),
        "engine": (
            "engines",
            "engines",
            p.get("engine_revision_id") or (setup.engine_version_id if setup else None),
        ),
    }
    for kind, (resource, route, revision_id) in component_versions.items():
        if not revision_id:
            continue
        try:
            version = access.library_version(session, principal, resource, revision_id)
        except ApiProblem:
            continue
        binding = library.binding_for(resource)
        obj = session.get(binding.object_model, getattr(version, binding.object_fk_name))
        result.append(
            RunReference(
                kind=kind,
                name=(version.summary or {}).get("physical_metadata", {}).get("name") or obj.name,
                revision_id=version.id,
                revision_number=version.version_number,
                href=f"/library/{route}/{obj.id}?revision={version.id}",
            )
        )
        if kind == "cvt" and version.belt_version_id:
            belt = access.library_version(session, principal, "belts", version.belt_version_id)
            obj = belt.belt
            result.append(
                RunReference(
                    kind="belt",
                    name=(belt.summary or {}).get("physical_metadata", {}).get("name") or obj.name,
                    revision_id=belt.id,
                    revision_number=belt.version_number,
                    href=f"/library/belts/{obj.id}?revision={belt.id}",
                )
            )
    for ref in result:
        if ref.kind == "setup" and setup:
            ref.href = f"/library/setups/{setup.vehicle_assembly_id}?revision={setup.id}"
            ref.revision_number = setup.version_number
        elif ref.kind in {"tune", "scenario"} and ref.revision_id:
            try:
                revision = experiments.get_revision(
                    session,
                    principal,
                    ref.revision_id,
                    "tunes" if ref.kind == "tune" else "scenarios",
                )
            except ApiProblem:
                continue
            route = "tunes" if ref.kind == "tune" else "load-cases"
            ref.href = f"/catalog/{route}/{revision.experiment_id}?revision={revision.id}"
            ref.revision_number = revision.number
    return result


def metric_values(run):
    values = (run.summary_scalars or {}).get("metrics", {})
    return [
        {"key": key, "label": label, "unit": unit, "value": values[key]}
        for key, (label, unit) in METRICS.items()
        if key in values
    ]


def history_item(run):
    return RunHistoryItem(
        run=jobs.status(run, include_provenance=False).model_copy(update={"summary_scalars": {}}),
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
    author_id=None,
):
    if since and until and since > until:
        raise ApiProblem(422, "date_range", "The start date must be before the end date.")
    if principal.account_id:
        jobs.recover(session, settings, principal.account_id)
    conditions = [Run.account_id == principal.account_id] if scope == "own" else []
    if author_id is not None:
        conditions.append(Run.created_by_user_id == author_id)
    if query.strip():
        escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        columns = (
            Run.name,
            Run.id,
            Run.provenance["setup_name"].as_string(),
            Run.provenance["tune_document"]["name"].as_string(),
            Run.provenance["scenario"]["name"].as_string(),
        )
        conditions.append(or_(*[column.ilike(f"%{escaped}%", escape="\\") for column in columns]))
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
    outcome = run_outcomes.outcome(run)
    return ResultAvailability(
        full_result=bool(full and full[2]),
        full_result_hash=full[1] if full else None,
        preview=outcome.has_data,
        partial=outcome.partial,
        original_row_count=(run.summary_series or {}).get("original_row_count"),
    )


def _run_selection(run):
    """Keep saved identities and run-only overrides distinct."""
    p = run.provenance or {}
    if (run.execution_options or {}).get("execution_profile", "default") != "default":
        raise ValueError(
            "This run uses a specialized execution profile. Use its original workspace or rerun the frozen input."
        )
    if not p.get("setup_revision_id") or not isinstance(p.get("scenario"), dict):
        raise ValueError(
            "This run has no saved setup/scenario references for the builder. Its exact input can still be exported or rerun."
        )
    return ExperimentSelection.model_validate(
        {
            "setup_revision_id": p["setup_revision_id"],
            "tune_revision_id": p.get("tune_revision_id"),
            "tune_values": p.get("tune_values"),
            "scenario_revision_id": p.get("scenario_revision_id"),
            "scenario": p["scenario"],
            "primary_boundary": p.get("primary_boundary"),
            "vehicle_mass_kg": p.get("vehicle_mass_override_kg"),
        }
    )


def experiment_unavailable_reason(run):
    try:
        _run_selection(run)
    except (ValueError, KeyError, TypeError):
        return (
            "This run cannot be opened in the experiment builder. "
            "Export or rerun its exact frozen input instead."
        )
    return None


def experiment_draft(session, principal, settings, run_id):
    """Read the original revisions into an unsaved builder session; create nothing."""
    run = access.public_run(session, run_id)
    reason = experiment_unavailable_reason(run)
    if reason:
        raise ApiProblem(422, "experiment_unavailable", reason)
    selection = _run_selection(run)
    # Comparing reconstructed JSON is cheap and catches unsupported historical
    # settings. Full CINDER validation remains at review/submission, not navigation.
    candidate, _, _ = experiments.configuration(session, principal, settings, selection)
    if any(
        candidate[key] != run.input_contract[key]
        for key in ("assembly", "shaft_boundaries", "host", "scenario", "execution")
    ):
        raise ApiProblem(
            422,
            "experiment_unavailable",
            "The saved references no longer reproduce this run's inputs. Export or rerun its exact input instead.",
        )
    version = access.library_version(
        session, principal, "vehicle-assemblies", selection.setup_revision_id
    )

    def selected_experiment(revision_id, kind):
        if revision_id is None:
            return None
        revision = experiments.get_revision(session, principal, revision_id, kind)
        return experiments.detail(session, principal, revision.experiment_id, revision.id)

    return RunExperimentDraft(
        source_run_id=run.id,
        selection=selection,
        setup=physical_library.selection_for_revision(session, principal, "setups", version.id),
        surface=tune_surface(session, principal, version.cvt_design_version_id),
        tune=selected_experiment(selection.tune_revision_id, "tunes"),
        load_case=selected_experiment(selection.scenario_revision_id, "scenarios"),
    )


def inspect_run(session, principal, settings, run_id):
    run = access.public_run(session, run_id)
    if principal.account_id == run.account_id:
        jobs.recover(session, settings, principal.account_id)
    summary = run.summary_scalars or {}
    return RunInspection(
        owned=bool(principal.account_id and principal.account_id == run.account_id),
        run=jobs.status(run),
        references=references(run, session, principal),
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
        experiment_unavailable_reason=experiment_unavailable_reason(run),
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
            [f"{column['key']} [{column['canonical_unit']}]" for column in table["columns"]]
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
