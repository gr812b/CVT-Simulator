# Reopen runs using their saved references

Follow-up to `146fbe7`. This patch fixes **New experiment from this run** only;
3D geometry and renderer behavior are unchanged. No database reset or migration is
needed. Apply the patch, restart the API and rebuild/restart the frontend so the
regenerated API types and routes agree.

## Cause

The old `experiment-copy` action rebuilt a new vehicle from the run's final input,
including a newly named `CVT from run`, engine, belt and load case. It baked tune
values into that CVT. The new CVT had a different identity, so the original CVT's
tunes were no longer associated with it. Creating and validating those physical
copies also made an action that looked like navigation unnecessarily expensive.

## Behavior

The action now opens `/input?source_run=...`. A read-only
`GET /runs/{run_id}/experiment` returns a generated, typed builder draft containing:

- The original vehicle, CVT, belt and engine version references.
- The original selected tune and load-case versions, even if newer versions exist.
- The original run's unsaved tune values, scenario edits, primary boundary and
  vehicle-mass override, held separately from the saved hardware.

Nothing is created or published by opening the builder. Repeated clicks/reloads
create no duplicates. The tune picker stays attached to the original CVT version.
Run-only road settings work even when the original run did not select a saved load
case. A mass override is explicitly labelled and can be reset to the saved vehicle
mass. A subsequent submission creates a new run linked to its source.

Actual edits to physical components still use the existing save/version workflow.
The old POST copy endpoint is removed. Explicit public-library copy actions are
unchanged. Copies already created by the old action are not deleted automatically;
reopen the original run to recover its original selections.

## Architecture

Pure configuration assembly is shared between draft restoration and normal
preview/submission. The draft verifies that its reconstructed input matches the
run's stored executable fields, without running CINDER mechanics validation.
Review and submission retain full validation. Unsupported or unavailable source
references produce an error; the action never silently invents replacement parts.

The frontend uses generated `RunExperimentDraft` and `PhysicalSelection` contracts.
It no longer requests/saves a reconstructed physical copy or fetches the latest
version instead of the pinned version. It also avoids a second physical validation
request during navigation. The default builder and explicit library-copy flows
remain available.

## Acceptance

Temporary API/browser checks cover default McMaster hardware, all five compatible
sample tunes, repeated read-only opens, a saved tune/load case, unsaved roads,
run-only primary/mass/tune/scenario overrides, and setup/tune/load-case versions
superseded after the source run. Database table counts are unchanged by opening a
draft. Reconstructed executable inputs match the frozen source, and new submissions
retain the parent-run link without physical-library or experiment-item writes.

Local draft reads took approximately 26–81 ms. The standard browser reopening
became visible in approximately 0.8 s in the local acceptance environment; these
are observations, not deployment latency guarantees. Type generation, TypeScript
production build, targeted ESLint and Python syntax/import checks pass. No unit
suite, committed browser suite or CI changes are included.
