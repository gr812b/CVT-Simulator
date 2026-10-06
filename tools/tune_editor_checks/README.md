# Tune preview, placement and inspection checks

## Current follow-up: quick previews, corner axes and the project note

`CINDER_Quick_Preview_And_About.patch` targets `front-end-redo-setup` at
`31d961e68f11402cf0d5e0fd3c596bcb724e2abe`, which contains the preceding tune
refinement. All ten affected starting files were matched to their GitHub blob
identities at this commit. It also applies after the earlier
`CINDER_Tune_Refinements.patch` on `b14d382a2775922676f9c04e1a02df27dd257fd7`;
do not apply it to that earlier commit without the refinement.

### Editing versus saving

The preview does **not** invoke `validate_assembly` or compile the dynamic map on
each edit. It keeps the lightweight shape validation, CINDER's existing contact
branch trace, and the profile/pose samples needed for the drawing. The contact
trace is back to the previous 129 base samples, with exact visible positions and
the travel endpoints included. Missing initial, interior or final contact still
produces a partial drawing and disables Save and temporary use. The first failing
sample is a diagnostic location, not an exact analytic contact-loss boundary.

A complete preview enables submission, not an assertion that the full assembly
has passed the construction audit. The **existing, independent save validator**
still performs the full CINDER check before accepting a tune. Run submission also
keeps its own full input validation. A problem not detected by the quick preview
can therefore still be rejected on Save. Neither full validator was weakened or
moved to the browser.

Current-draft and request-failure guards remain: a previous successful preview
cannot enable a changed draft, and incomplete numeric text blocks both actions.
The UI says "Updating contact preview…" instead of implying that it is running
the full construction audit while you edit. Name/description edits do not change
the preview input key.

### Inspection and homepage

The orientation triad is smaller and pinned to the bottom-right viewport edge.
The opaque frame card and its header are removed. Axis labels stay inside the
small SVG, and end-on labels appear below the triad instead of overlapping the
horizontal label. The overlay never intercepts pointer/wheel gestures. The
separate pivot/ramp-start and roller-1 labels remain, as do the default camera
orientations, travel scrubbing, rotation, zoom and Reset behavior.

The old "A note from me" section is now "About this project" with the four
paragraphs supplied by Kai, unchanged. It includes the email link
`mailto:kai@kaiarseneau.dev` and the Discord handle `Gr812b`. The handle is shown
as text, not an invented Discord user-ID URL. Paper, repository and demo links
remain unchanged.

### Apply

From the repository root:

```text
git apply --check /path/to/CINDER_Quick_Preview_And_About.patch
git apply /path/to/CINDER_Quick_Preview_And_About.patch
cd frontend
npm run build
```

Restart backend and frontend after applying. This follow-up does not change the
API response shape, dependencies or migrations. The normal frontend prebuild may
regenerate contracts as usual. No database reset, record deletion, solver-equation
change, deployment or remote Git write is included.

## Retained behavior from the preceding refinement

Primary ramp-start offsets are signed axial/radial distances from the fixed
pivot at fully open primary. They are saved as tune values and resolved into the
model's native ramp-reference coordinates, not applied just to the drawing.
Older tunes that omit them preserve their original placement. Moving the ramp
start does not move the pivot or prescribe an independent roller-contact point.

The primary companion plot shows evaluated CINDER ramp angle versus axial ramp
coordinate. The secondary uses helix angle versus actual usable opening. Exact
joins, contact coordinates and usable endpoints, plus interior samples in short
stages, remain included. Primary angle controls remain directly editable without
a conversion-confirmation gate. Opening does not rewrite the profile; an actual
profile edit writes shared endpoint angles and smooth joins. Unsaved-edit
confirmation remains.

## Executed focused checks

```text
python tools/tune_editor_checks/backend_checks.py
node tools/tune_editor_checks/frontend_checks.mjs
```

Backend: **25 passing checks**, using the production adapter functions, NumPy and
Pydantic with explicit CINDER and persistence doubles. The audit double raises
immediately if any edit preview tries to run the expensive construction check.
Tests cover repeated edits without audits, the bounded preview grid, shape
validation, missing initial/interior/endpoint contact, partial branches, coverage,
offsets and serialization, traces, and the unchanged Save validator performing
its full audit and rejecting a failed one independently of preview feedback.

Frontend: **30 passing helper/JSX-adapter checks**, plus syntax/transpilation of
**11 TypeScript/TSX files**. They cover current/stale/failed previews, Save/Use
gating, numeric drafts, profile editing, angles, orientation bases, the compact
transparent corner placement, preserved point labels, the exact four homepage
paragraphs, both contact details and the existing public links. The JSX adapter
is not real React, and transpilation is not a full TypeScript/application build.

An additional isolated Chromium DOM check rendered the actual overlay component
with JSX/camera/math adapters: primary and secondary at desktop and mobile widths
(four cases), with five viewing directions each. Corner bounds, readable label
bounds, a transparent background and pointer pass-through passed. This is **not**
a real CVT/WebGL scene test. Default primary/mobile and secondary/desktop overlay
screenshots were inspected; the end-on label overlap found there was corrected.

The preparation checkout contains the relevant recovered files rather than the
complete installed application. No full app build, real CINDER execution, live
preview timing or authenticated end-to-end journey was run. No speed multiplier
or absolute latency is claimed. Patch application/reversal and resulting-file
comparisons are checked separately against the prior delivery's file identities.

## Real-application acceptance

1. Change a ramp angle/offset repeatedly. Only the quick preview should run.
   Introduce contact loss at the start, middle or end; the missing portion stays
   hidden and Save/Use stay disabled. Restore contact and then Save: the full
   construction check runs at this explicit submission, not at each edit.
2. Check the compact axes in both mechanism previews while rotating and zooming,
   including end-on views. Point labels and camera behavior should be unchanged.
3. Verify "About this project", all four paragraphs, the email link and Discord
   handle at desktop and mobile widths.

A successful sampled contact preview is not proof of valid geometry between all
samples or compressive contact forces throughout a dynamic run. Full construction
validation and runtime contact-admissibility checks remain independent.
