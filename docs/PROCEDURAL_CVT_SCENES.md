# Landing page and procedural CVT scenes

This increment follows `5315854` (public workspace refinements). It replaces the
CVT CAD-loading path with a shared procedural viewer and refreshes the landing
page. The simulation model, queue, database schema, charts and research paper
are unchanged. Formal E2E coverage and testing CI remain deferred to M5.

## Product behaviour

- `/` shows one fixed default CVT. Visitors can orbit with a pointer or arrow
  keys; there are no radius, belt, shift, projection or transparency controls.
  The preview does not auto-rotate, pan, zoom or submit a simulation.
- Landing content describes the setup → road load → playback workflow, links
  the existing formulation paper and GitHub repository, credits Kai Arseneau,
  and leads directly to the account-free recorded demo.
- Demo, owned-run and public-run playback share procedural sheaves, shafts,
  hubs and the existing reported belt path. Playback keeps belt visibility,
  tension colouring, transparent sheaves, rotation, motion blur, orthographic
  projection, grids and cross-section controls.
- Geometry studies use the same meshes, with 21 resolved poses across the shift
  range. A labelled keyboard-accessible slider selects the pose. Rerunning a
  changed study replaces its meshes rather than retaining old model IDs.
- Page backgrounds show through the canvas, including the optional blur pass.
  The old grey scene background and external Draco/CAD requests are gone.

## Ownership and extension points

`backend/app/schemas/scene.py` defines the API projection. `CinderGateway` resolves
centre distance, radius envelopes and poses using CINDER's geometry spec and
public belt-path expressions. No integration, worker or fabricated simulation
result is needed for a geometry preview.

`GET /api/v1/demo/scene` is anonymous, fixed and cached in process. Its current
response is about 12 KB. It is independent of the much larger retained demo
artifact. Playback result envelopes include `scene_geometry`; the simple study
response includes `scene`. The retained demo artifact remains a separate schema
from its enriched HTTP response, including in the demo generation command.

Frontend API types are generated from OpenAPI. `sceneSpec.ts` is the one adapter
from those dimensions in metres to existing scene units. Its local types describe
rendering state, not a second API contract. `GeometryScene` adapts static preview
poses; `Scene3DViewer` adapts report replay. Both use `proceduralModels.ts`, the
same belt mesh, and `Scene3DController`.

The belt section is placed about the reported cord path using its actual cord
depth, rather than assuming that the path passes through mid-height. Playback
uses the recorded secondary radius to place its groove faces; it does not assume
secondary travel equals primary travel. The existing CINDER expression evaluator,
reported tensions, shaft-angle integration and helix-angle adapter remain in use.

These are explanatory geometry meshes, not manufacturing CAD. Hub sizes, shafts,
rim thicknesses, witness marks and material properties are illustrative. The
sheave faces surround the supplied belt radii and share the model's representative
belt plane; this does not introduce a distributed axial belt model or hardware
clearance verification. Measured belt and sheave angles may differ. Add future
hardware detail as rendering modules; keep mechanical closure and validation in
CINDER and regenerate transport types when projections change.

## Scene appearance and lifecycle

- `frontend/src/styles/theme.ts`: shared scene material palette, tessellation,
  lighting and pixel-density settings alongside the product theme.
- `sceneConfiguration`: common camera defaults and interaction policy.
- `Scene3DViewer.module.scss`: theme-based scene surface, options and legend.
- `Scene3DController`: transparent WebGL, resize observation, projection changes,
  bounds fitting, orbit controls and existing temporal rotation blur.

Pixel density is capped at 2. Static previews draw on demand, and scenes skip
rendering while offscreen, zero-sized or in a hidden document. Paused playback
reuses its belt geometry until the sample or view options change. Disposal clears
model resources, observers, controls, render targets and the WebGL context.
WebGL failure displays an inline explanation without breaking the surrounding
page; a failed sample request leaves the landing links and content available.

## Setup and acceptance

Apply this increment after the public workspace patch and restart the API and
frontend using the existing development instructions. There is no migration,
reseed or database wipe for this change. `npm run build` (and `npm run dev`)
regenerates backend/CINDER contracts as before. A worker is needed for new runs,
not for the landing preview, geometry study or recorded demo.

Validation completed with disposable acceptance scripts, without adding a unit
test suite or changing CI:

- Production contract generation, TypeScript and Vite build; targeted frontend
  ESLint and backend Ruff import/error checks.
- CINDER radius/path agreement at 63 poses across three scaled geometries;
  finite serialized projections, simple-study response and retained artifact
  validation.
- Chromium desktop and 390 px mobile review, no horizontal overflow, mouse and
  keyboard orbit, no landing form controls, no GLB or Draco downloads.
- Playback transparency, orthographic view, tension, rotation, blur, section and
  grid controls; owned-run playback and the fixed playback footer.
- Study endpoint navigation and changed-input mesh replacement; idle/offscreen
  rendering instrumentation; route disposal/re-entry; API and WebGL fallbacks.
- Transparent framebuffer corner during active blur. Software-rendered Chromium
  made large blur screenshots slow, so this check used a smaller viewport; this
  is not a hardware performance benchmark. Blur remains optional and off by
  default.

The existing Vite large-chunk warning remains (Three.js/chart dependencies).
The procedural Three.js scene chunk is about 139 KB gzipped; it does not fetch
any of the approximately 31 MB of legacy CAD assets. Existing paper/GitHub URLs
are preserved; live GitHub link verification was unavailable in this environment.
