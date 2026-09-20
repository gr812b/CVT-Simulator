# Source basis

Implementation read against the published CINDER 1.1.2 wheel and these shared Results files on `develop`:

| Source | Git blob / identity inspected |
|---|---|
| `defaults/baja/simulation_case.json` | `d9592cc664c8dfe095bda2cacdb9140beffb340b` |
| `defaults/reference_model/reference_case.py` | `c201d95fbda4ccfbbfb5b017ea7e454871bec018` |
| `defaults/reference_model/slotted_helix.py` | `bd08b47020413c56f9d934a1172d8506eae26f3e` |
| `defaults/reference_model/__init__.py` | `c80bbe8b38f9613bab06029ec9f1d1c89b3c7896` |
| CINDER release source commit | `7637a38b4fb9ec21dfb953c1c80a27ec5f389654` |
| Released wheel SHA256 | `f9c454963006d701b33197bdef3be60abebc591199aef7f4b52f37a7159310c3` |

The installed wheel was obtained from the existing release workflow artifact for testing; neither that wheel nor copied Results helpers are included in this add-on. The add-on imports the user's existing release environment and shared helpers. Each run hashes the actual local files so subsequent shared-input changes are visible.

Relevant packaged source interfaces: `cinder.execution.hybrid.integrate_hybrid`, `ComposedCVTHybridSystem`, `FixedPivotFlyweightForce`, `HelicalTorqueReactionForce`, `LockedFinalDriveShaftBoundary`, `FullThrottleEngineBoundary`, `RoadProfileSample`, `inspect_cvt_state`, and `recover_belt_tension_boundaries`.

The reference tip partition is the existing 0.013646 kg uniform arm plus 0.250 kg concentrated tip hardware per flyweight. Alternative hardware masses are exploratory input choices, not newly sourced commercial component specifications.

No new engine curve, rubber material data, controller law, or constitutive fit is introduced by this study.
