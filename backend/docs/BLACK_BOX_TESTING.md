# Application and API acceptance checks

Use a disposable database and QA accounts. Follow the [backend setup](../README.md)
for migrations, initialization, API and worker startup, then start the frontend.
API and worker must use the same database. The default browser app is
`http://localhost:5173`; API schemas are at `http://localhost:8000/docs`.

## Automated coverage

From the backend virtual environment:

```bash
python -m pytest
python -m pytest test/test_library_api.py test/test_api_journeys.py test/test_tune_preview_adapter.py
python -m pytest test/test_catalog_defaults.py test/test_scene_tip_mass.py test/test_tune_tip_mass_limits.py
```

The library/journey tests exercise the current authenticated API and durable job
contract. Focused adapter checks use explicit doubles; actual-CINDER mass and
catalog checks cover separate model/persistence behavior. Review a test's fixtures
before treating it as evidence of full solver execution. Browser adapter checks
and their dependencies are described in the [frontend guide](../../frontend/README.md#checks).

Automated checks do not establish delivery through a production SMTP provider,
production PostgreSQL operation, or the appearance/performance of a real WebGL
scene. Verify those in the appropriate environment when the change affects them.

## Authentication for direct API checks

Requests use the session cookie returned by registration/login. Mutations require
`X-Cinder-Client: web`; authenticated mutations also require the `X-CSRF-Token`
from the current session response. A supplied `Origin` must be allowed. The
frontend transport supplies these automatically. Do not send seed account/user
IDs to impersonate a user.

For manual `curl` checks with `jq`, create a temporary QA account against your
local disposable API (POSIX shell):

```bash
umask 077
API=http://localhost:8000/api/v1
curl -sS -c qa-cookies.txt "$API/auth/register" \
  -H 'Content-Type: application/json' \
  -H 'Origin: http://localhost:5173' \
  -H 'X-Cinder-Client: web' \
  -d '{"email":"qa-local@example.com","display_name":"Local QA","password":"local-qa-password"}' > qa-session.json
CSRF=$(jq -r '.csrf_token' qa-session.json)
curl -sS -b qa-cookies.txt "$API/auth/session"
```

For a protected mutation, add `-b qa-cookies.txt`, `-H 'X-Cinder-Client: web'`,
`-H "X-CSRF-Token: $CSRF"`, the allowed origin, and the endpoint's JSON body from
OpenAPI. Registration/login do not require a previous session's CSRF token.
Refresh the response token after login/password changes. Delete the QA session
files after testing; they grant access to the QA account. Use another unique
email if the disposable database already contains this account.

## Browser/API walkthrough

| Area | Check | Expected behavior |
| --- | --- | --- |
| Public reads | Sign out, browse physical items/tunes/load cases, then open `/demo` | Public content and the retained recording are readable without a worker |
| Sessions | Register, reload, edit profile, sign out and sign in | Session persists across reload; protected writes fail after logout |
| CSRF/ownership | Omit the client/CSRF header; try to edit another account's saved item | Mutation is rejected; public visibility does not confer write access |
| Physical items | Copy a sample, change a value, Save, inspect history, restore an older revision | The copy is independent; saved history remains fixed; restore creates a new revision |
| Tune selection | Change a tune, Save, edit/save the setup, then review/submit | The new tune ID/revision and edited values reach the submitted configuration |
| Compatible hardware | Change vehicle with the same CVT, then deliberately select a different CVT | Compatible tune stays selected; incompatible hardware receives a compatible tune |
| Run-only tune | Edit a tune and choose **Use for this run only** | Submitted values change without creating a library tune revision |
| Validation | Create incomplete/stale/contact-loss preview, then attempt Save | Invalid preview blocks the action; Save still performs its own full validation |
| Roads | Inspect the 200 m ±15°/±30° samples and edit a copied road | Length/angle edits persist; source sample remains unchanged |
| Queue | Submit with the worker stopped, retry the same request key/payload, then use a new key | First returns 202/queued, identical retry identifies the same job, another active job is rejected |
| Execution | Start the worker for a short valid run and refresh its page | Status progresses from queued/running to a terminal state with retained results when produced |
| Cancellation | Cancel a queued run, then a running run | Queued cancellation is immediate; running cancellation stops its child before releasing the slot |
| History | Edit source objects after completion, export the run, reopen/reuse it | Frozen input and old results stay fixed; reopening references does not create library copies |
| Recovery | Interrupt a disposable worker after a checkpoint, restart, wait through deadline/grace | Orphan is recovered and saved progress remains available; no automatic solver resume |
| Result display | Seek/play at desktop/mobile widths, inspect charts/forces and export CSV | Cursor and available data agree; terminal partial results remain inspectable |

For request-key checks, use a unique UUID per intended new submission. Reuse with
different content must conflict rather than silently returning another result.
Keep the actual CINDER case short enough for the configured limits; HTTP 202 is
admission, not completion. Inspect `/runs/{id}/input`, `/preview`, `/result` and
the current run status to distinguish acceptance from execution.

## Password reset

Register a QA account with a password, request a reset, and decode the latest
local outbox message using the [email instructions](../README.md#accounts-and-password-reset-email).
Open the link through the configured web origin, set a new password, and verify
old credentials/sessions and the used link no longer work. Requesting another
link invalidates the previous one. Unknown/passwordless accounts return the same
generic message without creating mail. In production, repeat with a real test
inbox and the configured SMTP provider; inspect API logs on delivery failure.

## Useful failure evidence

Record the endpoint/status, visible error code, run ID and configured limits.
Use API logs for authentication/mail/admission errors and worker logs for child
startup, memory, timeout or solver failures. Do not include cookies, passwords,
reset links or real account email in shared logs. A retained partial result should
be inspected alongside its stop reason rather than described as a completed run.
