# Production M170 replacement

Source: gr812b/CVT-Simulator, results-latex, commit
5a26e5aecae52a96138cc7d63dd948d24cb97030.

Selection: section4p5-final-v3-r26b7-m170.
D02_M170 replaces D02_M150 in the selected thirteen-car course fleet and
all three presentation groups that referenced it. The two supporting flat
runs remain unchanged. This is the production study, not exploration.

The only new physical input is tip_mass_scale = 1.7 instead of 1.5.
The replaceable tip is 0.425 kg per flyweight. The original tune resolver
updates total mass and both mass moments; primary_preload_scale stays 1.15.
The course, numerical settings, mechanics, shared defaults and remaining
case definitions are unchanged. The selection lock is regenerated for this
explicit revision; selection validation remains enabled.

M170 has not been simulated here. Historical M150 evidence in FINAL_SELECTION_V3.md,
TEST_REPORT.md and LOCAL_TEST_RECORD.json still describes M150, not M170.

The runner's suite fingerprint changes, producing a new output folder.
--resume reuses only matching outputs in the new revision; it does not
import old M150-suite results. The usual full command reruns all 15 cases.
Running --only unified_course/D02_M170 is supported by the production
runner, but the report will be incomplete (exit code 2) until the rest of
the selected suite is present.
