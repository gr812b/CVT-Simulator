# Public demo and worker startup follow-up

> Current setup and visibility policy: [Public workspace refinements](PUBLIC_WORKSPACE_REFINEMENTS.md). This historical milestone document may describe superseded private-data or migration behavior.

This follow-up fixes the manual-testing experience after M4. It does not begin M5's formal test suite or CI work, and does not change CINDER mechanics or its 1.1.4 pin.

## Apply and run

After applying the follow-up patch, stop the old API and worker. Activate the backend environment and install the updated requirements once:

```bash
cd backend
source venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

In a second backend terminal with the same database environment:

```bash
source venv/bin/activate
python -m app.scripts.run_worker
```

Restart `npm run dev` in `frontend/` so it regenerates the API types. This update adds `psutil` for portable process-memory monitoring; it needs no database migration, reseeding or frontend dependency installation.

Open `http://localhost:5173/demo` to test playback. The API and frontend must be running. A worker, account and initialized database are not required for this public demo. Ordinary personal simulations still require the worker and the normal database setup. Native Windows can serve the recorded demo, but running new jobs still requires Linux/WSL/Docker rather than the native Windows worker.

## Why the old error was unhelpful

The old child applied resource limits and imported the solver outside its exception handler, while its parent discarded standard error. A resource-limit setup failure, missing Python module, native crash or external termination could all surface as the same “stopped without a result” message. That message alone cannot establish which happened on a particular machine.

The updated worker uses the backend package directory explicitly when launching a child, continuously drains its standard error, and keeps at most the last 16 KiB for private worker-terminal diagnostics. API errors distinguish startup/import failures, memory budget, wall-clock timeout, result-size limit and process exit code/signal. Detailed tracebacks are written to the worker log, not exposed through public API responses. Completed output is installed atomically.

Linux retains its kernel address-space limit. On macOS, the worker avoids that Linux-style address-space cap and instead monitors the child's resident memory through `psutil`. The same resident-memory watchdog also runs on Linux. It samples at most every 0.5 seconds; macOS can briefly overshoot the configured threshold between samples. Both platforms retain the independent child wall-clock alarm and file-size limit. The worker does not attempt to raise an inherited hard resource limit. Cancellation still releases the account slot only after the child has stopped.

If a new run still fails after updating, copy its new error and the corresponding `cinder.worker` / `cinder.child` traceback from the worker terminal. Old failed runs keep their original error; use **Rerun frozen inputs** to exercise the updated worker.

## Recorded demo

`GET /api/v1/demo` is an anonymous, read-only endpoint serving `backend/app/demo/baja-launch.json.gz`. The bundle contains the canonical input, full CINDER result, runtime identity, generation timestamp and hashes of both input and result. It was generated from the existing Baja baseline with a ten-second duration and 20 ms reporting grid, producing 533 report rows including transition samples. It is actual solver output, not fabricated or recalculated display data.

Opening or refreshing `/demo` never submits a job or writes a run/account record. It does not read another user's history or replace the signed-in user's selected result. The demo and private run routes share `SimulationPlayback`, including the 3D viewer, graphs, playback controls and full-report CSV download. Public navigation returns to Home or the public library.

Regeneration is an explicit developer operation, not application startup or seeding:

```bash
cd backend
source venv/bin/activate
python -m app.scripts.build_demo
```

The generator preserves the baseline's physical values, runs an isolated bounded child, rejects incomplete results and atomically replaces the compressed artifact. Review and commit that artifact when deliberately updating the demo. API processes cache it for their lifetime, so restart the API after replacing it.

## Verification

Focused disposable checks outside the repository cover a real Linux worker run, injected startup failure with retained diagnostics, memory-budget termination, independent child timeout, cancellation, and simulated selection of Darwin's resource limits without `RLIMIT_AS`. The macOS branch has not been executed on actual macOS hardware in this workspace.

The anonymous browser walkthrough uses an uninitialized database and no worker: Home → View Demo, playback controls, seeking, speed changes, full CSV download, direct reload, narrow-screen layout and retry after a failed demo response. Generated API contracts, production build and frontend lint are checked; the two pre-existing hook warnings remain. M5's formal E2E/CI and production release checks remain deferred.
