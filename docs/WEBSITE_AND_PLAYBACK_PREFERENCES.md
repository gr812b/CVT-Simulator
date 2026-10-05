# Website content and playback preferences

Incremental update after `dd9fc4c` / `CINDER_Playback_Balances_And_Scene.patch`.

## Apply

Extract the ZIP. From the repository root, with the previous patch already applied:

```powershell
git apply --check CINDER_Website_And_Playback_Preferences.patch
git apply CINDER_Website_And_Playback_Preferences.patch
cd frontend
npm run dev
```

Use the actual extracted patch path if it is outside the repository. If Vite is
already running, it reloads the changed frontend modules. For a production
frontend, run `npm run build` and serve the rebuilt `dist` directory as usual.
There are no dependency, database, worker, physics, or retained-demo changes.

## Behavior

- Home retains the existing visual design and headline. The copy explains
  hardware inputs, tunes, road loads, playback, forces, and exports. The paper
  uses its DOI. Kai's separate note identifies the website/interface as
  AI-generated and explains the intended use and limitations. The quoted
  energy remainder is scoped to the paper's reference acceleration case;
  experimental validation is not claimed. Source and license links remain.
- Workspace shows recent/active runs, a hill-course demo entry, and a short
  setup guide. It no longer fetches a whole default hardware setup or offers
  a separate baseline-launch form. Build a run owns that workflow.
- Demo header and playback share a gutter, including the fixed player.
- Both boundary shafts extend in the primary shaft's direction; sheave and
  actuator motion are unchanged. The renderer's fitting envelope includes
  the longer secondary shaft.
- Fullscreen keeps the existing scene and replay. It includes the same player,
  synced play/pause, seeking and speed, and supports Escape. Force menus stay
  inside the fullscreen surface. The tension key stays above the player.
- Forces open with both pulleys selected; primary/secondary filters remain.
  Transparency has one control in the scene toolbar.
- Playback and time-history charts share separate legend/tool rows and compact
  margins. Scrollable series keys keep their full labels on hover. Rectangle
  zoom, wheel zoom, restore, export, and plot click-to-seek remain.
- Scene and plot preferences are saved locally in the browser, shared between
  demo/results. Scene controls include force filtering, components, scale and
  labels. Plot settings include category, selected plots, hidden series, and
  the time-history signal. Reset scene, Reset plots, and Reset chart restore
  their respective defaults. Reset scene also restores the camera.
- Camera orientation, axis ranges, playback time, running state, fullscreen,
  and open menus are not stored across runs. Axis ranges still survive plot
  tab switches within a mounted replay. Invalid saved preferences recover to
  defaults. No account synchronization or backend preference fields are added.
- Play and pause share theme-colored icons. Navigation uses a panel-collapse
  button inside the sidebar and a labelled expand action when collapsed.

## Verification

- Production build and generated API contracts pass.
- ESLint: no errors; two existing hook warnings in the older primary-design
  and validation pages.
- Direct checks cover preference round trips and malformed storage, replay
  speed notifications, fixed/moving colors and transparency restoration,
  common shaft direction and camera bounds, and chart layout at 280/420/760 px.
- A server-rendered chart was visually inspected. Browser access to the local
  preview was blocked by the execution environment, so full-page appearance,
  native fullscreen, pointer interaction, and storage across actual reloads
  still need manual browser verification. No automated E2E, unit-test suite,
  or CI changes are included.
