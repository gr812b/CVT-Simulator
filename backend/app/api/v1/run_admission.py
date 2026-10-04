"""Cheap HTTP checks before expensive CINDER preflight; final admission is atomic."""

import json

from app.application import jobs
from app.application.auth_limits import throttle
from app.core.errors import ApiProblem


def submission_attempt(http, session, principal, settings, key, payload):
    principal.require_write()
    try:
        if (
            len(json.dumps(payload, allow_nan=False).encode())
            > settings.run_max_input_bytes
        ):
            raise ValueError("The submission exceeds the configured input-size limit.")
    except (TypeError, ValueError) as exc:
        raise ApiProblem(422, "invalid_submission", str(exc)) from exc
    previous = jobs.existing_request(session, principal, key, payload)
    if previous:
        return previous
    jobs.check_available(session, principal.account_id, settings)
    # Count rejected/invalid attempts independently of the request transaction.
    # Accepted runs also have a stricter rolling-window limit inside admission.
    throttle(
        http,
        "simulation_submission",
        principal.account_id,
        limit=settings.run_submission_limit * 4,
        seconds=settings.run_submission_window_seconds,
        error_code="run_submission_rate_limit",
        message="Too many simulation submission attempts. Please wait before trying again.",
    )
    return None
