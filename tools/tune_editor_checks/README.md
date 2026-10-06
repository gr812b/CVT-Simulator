# Tune contact, placement and inspection refinements

Incremental patch base: `gr812b/CVT-Simulator`, `front-end-redo-setup`,
`b14d382a2775922676f9c04e1a02df27dd257fd7` (the previously delivered tune UI).
All ten existing files changed by this patch were checked against GitHub blob
identities at that commit. This is not the earlier cumulative patch.

## Behaviour

The tune preview now carries the same content-keyed CINDER construction audit
used by the existing save validator. Save and temporary-use actions require a
successful result for the current CVT revision and values. They are disabled
while checking, on request failure, on invalid numeric text, or when geometry
fails. An older preview cannot authorize a changed draft. Partial diagnostic
geometry may still be drawn to help repair an invalid draft; the first missing
contact sample is marked. It is a sampled diagnostic, not a claimed exact
analytic contact-loss boundary. The full construction audit remains decisive.

Primary ramp-start axial and radial offsets are signed distances relative to
the fixed pivot, in the fully open reference configuration. Positive radial is
outward; positive axial follows the model's positive primary closing direction.
They are persisted as tune values and resolved into the existing native ramp
reference coordinates. Pivot, arm length and source CVT remain unchanged.
Older tunes omitting these keys retain their original referenced placement.
The starting tip is not an independently prescribed roller-contact point.

Focused scenes use a presentation-only rigid parent transform. Primary radial
is up and its axial/radial profile plane faces the initial camera. The secondary
shaft is upright and roller 1 faces the initial camera near the top of the slot.
Ordinary orbiting therefore turns around that shaft. The labelled corner axes
follow camera orientation; secondary radial/tangent axes refer to roller 1.
Pivot/ramp-start or roller-1 markers explain the reference frame. Scrubbing does
not re-fit the camera. Reset fits current geometry and restores the default view.
Landing and playback transforms are unchanged.

The primary companion plot now shows evaluated CINDER ramp angle versus axial
profile coordinate, with stage selection and a contact-position marker. The
secondary plot continues to show helix angle versus actual usable opening.
Exact joins, contact coordinates and usable endpoints, plus interior samples in
short stages, are included in the backend traces. Primary angle controls no
longer require a conversion-confirmation step. Opening does not change saved
curvature; an actual profile edit writes shared endpoint angles with automatic
smooth joins. The nonblocking description makes this conversion explicit.

## Apply and rebuild

From the repository root, after saving/committing unrelated local work:

```text
git apply --check /path/to/CINDER_Tune_Refinements.patch
git apply /path/to/CINDER_Tune_Refinements.patch
cd frontend
npm run build
```

The normal prebuild regenerates API contracts from the updated backend. Do not
hand-edit generated contracts. Restart backend and frontend together: the new
preview validation field is required. A stale backend response is deliberately
rejected rather than interpreted as approval to save.

No database migration/reset, record deletion, solver equation change, deployment
or remote Git write is part of this patch.

## Focused checks executed during preparation

Run these independently from the repository root:

```text
python tools/tune_editor_checks/backend_checks.py
node tools/tune_editor_checks/frontend_checks.mjs
```

Backend: **23 passing checks**, using actual adapter functions, NumPy and
Pydantic, with explicit CINDER-geometry/audit and persistence test doubles.
They cover signed-offset mapping and serialization, original placement,
missing initial/late/endpoint contact, incomplete branches, interval coverage,
exact trace sampling, required validation response, no input/cache mutation,
and the existing save validator rejecting a failed audit independently.
This does not execute the real CINDER contact solver or a database transaction.

Frontend: **25 passing helper/JSX-adapter checks**, plus syntax/transpilation of
all **9 changed TypeScript/TSX files**. They cover current-draft validation,
late/stale reports, disabled Save/Use, invalid numeric drafts, custom primary
editing, angle plots, stage selection, helix bounds and orientation matrices.
A focused semantic check covers the fixed-arity Matrix4.set tuple signature.
The JSX adapter is not React: these are not browser interaction tests or a
substitute for a full TypeScript/application build.

A final local check applies and reverses the patch against the verified source
baseline, compares the resulting file bytes, and reruns the focused suites from
the applied tree. No application or generated-contract build was possible in
the preparation environment: the complete dependencies were unavailable and
package/repository downloads from the execution container failed DNS resolution.

## Real-application acceptance checks still required

These were **not run** during patch preparation:

1. Build with real generated contracts and installed dependencies. Open a valid
   tune; Save/Use stay disabled until the current audit completes. Make a late-
   travel and an endpoint contact failure. Both actions stay disabled. Repair
   the geometry; neither an old response nor a failed request enables actions.
2. Change both signed ramp offsets, verify the pivot stays fixed, save/reopen,
   and confirm the preview, retained values and resolved simulation input agree.
   Check an older tune without these fields keeps its original placement.
3. Inspect both initial views, pan/orbit/zoom, scrub all travel and verify camera
   stability. Reset after changing the ramp size. Check corner axes and named
   reference points while rotating and at end-on views. Verify landing/playback
   scenes retain their existing orientation.
4. Open a custom primary profile and close unchanged: no dirty prompt and no
   profile rewrite. Edit an angle directly without a conversion dialog; inspect
   the angle plot and sampled contact marker. Verify ordinary unsaved-edit
   confirmation remains, including for incomplete numeric text.

Geometrical validity is not a promise of compressive actuator reaction throughout
an arbitrary dynamic run. This patch prevents invalid geometry from being saved
or selected; it does not replace CINDER's runtime contact-admissibility checks.
