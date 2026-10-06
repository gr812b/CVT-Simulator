"""Explain run outcomes without inferring user fault from arbitrary exceptions.

Queue status describes execution. A completed execution may contain a deliberate
course stop; a saved checkpoint does not prove either completion or vehicle
failure. Public explanations use known reason codes and stored accepted samples,
never a traceback or an unclassified exception message.
"""

from __future__ import annotations

import math

from sqlalchemy import inspect

from app.core.errors import ApiProblem
from app.database import runs as artifacts
from app.schemas.runs import RunOutcome

COURSE_STOP_REASONS = {"time_limit", "rollback_limit", "no_forward_progress"}
MODEL_LIMIT_REASONS = {
    "mechanism_contact_unsupported",
    "contact_loss_normal_resultant_floor",
    "lower_shift_stop_reached_stop_reaction_unimplemented",
    "upper_shift_stop_reached_stop_reaction_unimplemented",
    "no_admissible_stick_or_direction_consistent_kinetic_branch_at_slip_zero_crossing",
    "no_direction_consistent_kinetic_branch_after_static_capacity_loss",
}
NUMERICAL_REASONS = {"numerical_failure", "maximum_transitions"}
CONFIGURATION_REASONS = {"invalid_simulation_case", "invalid_configuration", "run_limits"}
RESOURCE_REASONS = {
    "run_timeout",
    "run_memory_limit",
    "run_result_size_limit",
    "run_result_limit",
}
SERVICE_REASONS = {
    "worker_failure",
    "worker_interrupted",
    "worker_parent_changed",
    "worker_process_stopped",
    "queue_timeout",
    "solver_version_changed",
    "solver_import_failed",
    "resource_limits_failed",
    "result_persistence_failed",
    "checkpoint_persistence_failed",
    "child_protocol_error",
}


def _number(value):
    return (
        value
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        else None
    )


def preview_progress(preview):
    """Return only the extent represented by finite, saved simulation samples."""
    columns = {
        column.get("key"): column.get("values", [])
        for column in preview.get("columns", [])
        if isinstance(column, dict)
    }
    times = columns.get("time_s", [])
    if not isinstance(times, list):
        return False, None, None
    last = next(
        (
            index
            for index in range(len(times) - 1, -1, -1)
            if _number(times[index]) is not None
            and any(
                isinstance(values, list)
                and index < len(values)
                and _number(values[index]) is not None
                for key, values in columns.items()
                if key != "time_s"
            )
        ),
        None,
    )
    if last is None:
        return False, None, None
    distances = columns.get("vehicle.distance", [])
    distance = (
        _number(distances[last]) if isinstance(distances, list) and last < len(distances) else None
    )
    return True, _number(times[last]), distance


def saved_progress(run):
    progress = preview_progress(run.summary_series or {})
    if progress[0] or run.status not in {"completed", "failed", "timed_out", "cancelled"}:
        return progress
    # Historical runs may keep their preview only as a durable/cache artifact.
    # Current checkpoints already populate summary_series, and active polling
    # never needs this additional lookup. Detached records remain pure reads.
    state = inspect(run, raiseerr=False)
    session = state.session if state is not None else None
    if session is None:
        return progress
    try:
        preview = artifacts.get_database_run_preview(session, run.id)
    except ApiProblem as exc:
        if exc.code != "run_preview_missing":
            raise
        return progress
    return preview_progress(preview)


def result_completion(result):
    """Classify a child result before the queue releases its running slot.

    Deliberate course stops are finished executions with an incomplete course.
    A checkpoint, unsupported model state, or numerical stop is never success.
    """
    metrics = result.get("metrics", {})
    reason = metrics.get("termination_reason") or "incomplete_result"
    if reason in COURSE_STOP_REASONS:
        return "completed", None
    if reason in MODEL_LIMIT_REASONS | NUMERICAL_REASONS:
        return "failed", {"code": reason, "message": "The simulation stopped before completion."}
    if metrics.get("completed") is True and reason != "checkpoint":
        return "completed", None
    return "failed", {
        "code": "incomplete_result",
        "message": "The worker returned an unfinished simulation result.",
    }


def outcome(run):
    metrics = (run.summary_scalars or {}).get("metrics", {})
    error = run.error or {}
    has_data, reached_time, reached_distance = saved_progress(run)
    reason = error.get("code") or metrics.get("termination_reason") or run.status

    category, severity = "internal_error", "error"
    title = "Simulation error"
    message = "An internal simulation error stopped this run. This does not establish that the vehicle failed the course."
    action = "Report this run ID so the detailed worker error can be investigated."

    if run.status in {"queued", "validating", "running"}:
        category, severity, reason = "pending", "info", run.status
        title = "Run in progress" if run.status == "running" else "Run queued"
        message = (
            "The simulation is running."
            if run.status == "running"
            else "The run is waiting for a worker."
        )
        action = None
    elif run.status == "cancelled":
        category, severity, reason = "cancelled", "info", "cancelled"
        title, message = "Run cancelled", "The run was cancelled."
        action = "Open the saved data to review the run so far." if has_data else None
    elif reason in RESOURCE_REASONS or run.status == "timed_out":
        category, severity = "resource_limit", "warning"
        if reason == "run_timeout" or run.status == "timed_out":
            reason, title = "run_timeout", "Compute time limit"
            message = "The run reached the service's wall-clock time limit. This does not show whether the vehicle could finish the course."
            action = "Try a shorter simulation; if the same setup repeatedly reaches the limit, report this run ID."
        elif reason == "run_memory_limit":
            title = "Memory limit"
            message = "The simulation exceeded the worker's memory budget."
            action = "Try a shorter simulation or fewer reported samples."
        else:
            title = "Result storage limit"
            message = "The simulation output exceeded the service's result-size limit."
            action = "Reduce reporting detail or shorten the simulation."
    elif reason in CONFIGURATION_REASONS:
        category, severity = "configuration_error", "warning"
        title = "Configuration needs attention"
        message = "The run's input did not pass the simulation requirements."
        action = (
            "Open the run configuration and review the validation messages before submitting again."
        )
    elif reason in MODEL_LIMIT_REASONS:
        category, severity = "model_limit", "warning"
        title = "Model contact limit"
        if reason == "mechanism_contact_unsupported":
            message = "CINDER encountered a pulley-mechanism contact state this model does not support. Lift-off or contact on the opposite flank is not modeled for that mechanism, so the simulation stopped."
        elif reason == "contact_loss_normal_resultant_floor":
            message = "The belt reached the modeled contact-force limit. CINDER cannot continue in the resulting contact state."
        else:
            message = "The simulation reached a contact or shift-stop state that the current model cannot continue."
        action = "Review any saved data only up to the saved point. Report this run ID for model support; this outcome does not prove the vehicle could not finish."
    elif reason in NUMERICAL_REASONS:
        category, severity = "numerical_error", "error"
        title = "Numerical solver stopped"
        message = "The numerical solver could not continue reliably. This does not establish that the vehicle failed the course."
        action = "Review any saved data up to the saved point and report this run ID if the problem persists."
    elif reason in SERVICE_REASONS:
        category, severity = "service_error", "error"
        title = "Run service error"
        if reason == "result_persistence_failed":
            title, message = "Result storage failed", "The service could not save the final result."
        elif reason == "checkpoint_persistence_failed":
            title, message = (
                "Result storage failed",
                "The service could not save the latest simulation checkpoint.",
            )
        elif reason == "queue_timeout":
            title, message = (
                "Worker unavailable",
                "No worker started the run before its queue deadline.",
            )
        elif reason == "solver_version_changed":
            title, message = (
                "Solver version changed",
                "The installed solver changed after this run was submitted.",
            )
        else:
            message = "The simulation service could not finish this run. This is not a vehicle or tune failure."
        action = "Retry as a new run. If the problem persists, report this run ID."
    elif not error and reason in COURSE_STOP_REASONS:
        category, severity = "vehicle_stopped", "warning"
        if reason == "rollback_limit":
            title = "Rollback limit reached"
            message = "The simulated vehicle rolled back by the configured stopping distance before reaching the finish."
        elif reason == "no_forward_progress":
            title = "No forward progress"
            message = "The simulated vehicle did not make enough forward progress within the configured stopping interval."
        else:
            title = "Course not finished in time"
            message = "The simulated vehicle did not reach the finish within the configured simulation duration."
        action = "Review the saved speed, distance and force data, then adjust the setup, tune or course limits as needed."
    elif not error and run.status == "completed" and metrics.get("completed") is not False:
        category, severity = "success", "success"
        title = "Course completed" if reason == "course_finish" else "Run completed"
        message = (
            "The simulated vehicle reached the course finish."
            if reason == "course_finish"
            else "The simulation reached the requested end time."
        )
        action = None

    return RunOutcome(
        category=category,
        reason=reason,
        severity=severity,
        title=title,
        message=message,
        action=action,
        has_data=has_data,
        partial=has_data and category != "success",
        reached_time_s=reached_time,
        reached_distance_m=reached_distance,
        support_run_id=run.id,
    )
