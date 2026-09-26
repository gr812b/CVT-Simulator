"""Retain numerical evidence without merging the sides of hybrid events."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sys

import cinder
import numpy as np

from .simulation import compact_mode


def retain_result(setup, result, output: Path) -> None:
    """Save native states, segmented report channels and a common dense grid.

    Every segment retains both endpoints. Duplicate event times are intentional;
    consumers must plot segments separately. The comparison grid uses the
    successor segment at an event and never interpolates across a reset.
    """
    raw = result.trace
    time = np.concatenate([s.time for s in raw.segments])
    state = np.concatenate([s.state for s in raw.segments], axis=1)
    ids = np.concatenate([np.full(s.time.size, i, dtype=int)
                          for i, s in enumerate(raw.segments)])
    np.savez_compressed(output / "native_trace.npz", time_s=time,
                        full_state=state, segment_id=ids)

    channels = tuple(result.segments[0].signals)
    reported = {k: np.concatenate([s.signals[k].values for s in result.segments])
                for k in channels}
    reported["time_s"] = np.concatenate([s.time for s in result.segments])
    reported["segment_id"] = np.concatenate([
        np.full(s.time.size, i, dtype=int) for i, s in enumerate(result.segments)])
    np.savez_compressed(output / "segmented_report.npz", **reported)

    grid = np.arange(0.0, raw.final_time + 1e-12, 0.0002)
    values = np.full((state.shape[0], grid.size), np.nan)
    for segment in raw.segments:
        selected = np.flatnonzero((grid >= segment.start_time) &
                                  (grid <= segment.end_time))
        if selected.size:
            values[:, selected] = segment.dense_state_at(grid[selected])
    if not np.all(np.isfinite(values)):
        raise RuntimeError("Uncovered common-grid state in retained Ballew trace")
    cvt = setup.system.layout.view_matrix(values, "cvt")
    np.savez_compressed(output / "comparison_grid.npz", time_s=grid,
                        full_state=values, cvt_state=cvt)

    events = []
    for event in raw.transitions:
        events.append({"time_s": event.time,
                       "reason": event.transition.reason,
                       "fired_events": event.fired_event_names,
                       "previous_mode": compact_mode(event.previous_mode),
                       "next_mode": compact_mode(event.transition.next_mode),
                       "post_state": event.post_transition_state.tolist()})
    durations = Counter()
    for segment in raw.segments:
        durations[compact_mode(segment.mode)] += segment.end_time - segment.start_time
    steps = np.concatenate([np.diff(s.time) for s in raw.segments])
    record = {"segments": [{"id": i, "start_s": s.start_time,
                            "end_s": s.end_time, "mode": compact_mode(s.mode),
                            "native_samples": s.time.size}
                           for i, s in enumerate(raw.segments)],
              "events": events, "mode_duration_s": dict(durations),
              "transition_reasons": dict(Counter(e["reason"] for e in events)),
              "accepted_steps": int(steps.size),
              "native_step_quantiles_s": np.quantile(steps, [0, .5, .95, 1]).tolist(),
              "comparison_grid_step_s": 0.0002,
              "event_sides_preserved": True}
    (output / "trace_manifest.json").write_text(json.dumps(record, indent=2) + "\n")


def record_execution(study: Path, output: Path, solver: dict) -> None:
    """Freeze the exact study sources and identify every retained output."""
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    paths = [p for p in study.rglob("*.py") if "artifacts" not in p.parts]
    paths += [study / "study.json", study / "reference/manifest.json"]
    paths += list((study / "reference").glob("*.csv"))
    snapshots = output / "execution_inputs"
    inputs = {}
    for path in sorted(paths):
        name = path.relative_to(study)
        target = snapshots / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        inputs[str(name)] = sha(path)
    outputs = {p.name: sha(p) for p in sorted(output.iterdir())
               if p.is_file() and p.name != "execution_provenance.json"}
    record = {"cinder_version": cinder.__version__,
              "cinder_tag_commit": "7637a38b4fb9ec21dfb953c1c80a27ec5f389654",
              "cinder_module_path": str(Path(cinder.__file__).resolve()),
              "python_version": sys.version, "solver": solver,
              "input_sha256": inputs, "output_sha256": outputs}
    (output / "execution_provenance.json").write_text(json.dumps(record, indent=2) + "\n")
