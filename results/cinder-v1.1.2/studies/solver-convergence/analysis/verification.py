"""Fail-closed audits for publication of the retained convergence evidence."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np

from .evidence import (STUDY, GROSS_KEYS, rows, read_json, verify_record,
                       gross_rms, selected_row)


def formal_module():
    spec = importlib.util.spec_from_file_location("solver_formal_verification", STUDY / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def passes(row, guards):
    if row["run_status"] != "completed" or not row["transition_signature_match"]:
        return False
    return all(math.isfinite(row[k]) and row[k] <= guards[k] for k in (
        "trajectory_rms_normalized", "trajectory_max_abs_normalized",
        "maximum_event_time_error_s", "regime_mismatch_fraction"))


def audit_cache(path, formal):
    segments = read_json(path / "segments.json")
    transitions = read_json(path / "transitions.json")
    payload = formal.load_segment_traces(path / "segment_traces.npz")
    meta = read_json(path / "metadata.json")
    assert meta["completed"] and meta["final_time_s"] == 10.0
    assert len(segments) == len(transitions) + 1 == int(payload["segment_count"][0])
    assert np.array_equal(payload["phase"], np.linspace(0, 1, 2049))
    assert segments[0]["start_time_s"] == 0 and segments[-1]["end_time_s"] == 10
    events = []
    for i, seg in enumerate(segments):
        data = formal.unpack_segment_trace(payload, i)
        assert data["start_time_s"] == seg["start_time_s"]
        assert data["end_time_s"] == seg["end_time_s"]
        assert data["end_time_s"] >= data["start_time_s"]
        assert all(np.isfinite(data[k]).all() for k in formal.STATE_KEYS)
        if i >= len(transitions):
            continue
        event = transitions[i]
        following = segments[i + 1]
        assert seg["end_time_s"] == event["time_s"] == following["start_time_s"]
        assert event["previous_mode"] == seg["mode"]
        assert event["next_mode"] == following["mode"]
        right = formal.unpack_segment_trace(payload, i + 1)
        jumps = {k: float(right[k][0] - data[k][-1]) for k in formal.STATE_KEYS}
        # This endpoint audit is deliberately separate from the archived signature
        # flag, which says a successor state exists, not that velocity changed.
        physical_jump = any(abs(jumps[k]) > 1e-12 for k in formal.STATE_KEYS if k != "shift_m")
        assert abs(jumps["shift_m"]) < 1e-10
        events.append({**event, "endpoint_jumps": jumps,
                       "velocity_jump_above_1e_12": physical_jump})
    return {"segments": segments, "events": events, "payload": payload,
            "velocity_jump_count": sum(r["velocity_jump_above_1e_12"] for r in events)}


def close(a, b):
    return (math.isnan(a) and math.isnan(b)) or math.isclose(a, b, rel_tol=2e-11, abs_tol=2e-15)


def audit(artifacts):
    record = verify_record(artifacts)
    spec = read_json(STUDY / "study.json")
    summary = read_json(artifacts / "summary.json")
    for key in ("reference", "main_sweep", "absolute_tolerance_sweep", "canonical", "review_guards"):
        assert spec[key] == summary["study"][key], f"Different study definition: {key}"
    main = rows(artifacts / "main_sweep.csv")
    atol = rows(artifacts / "absolute_tolerance_sweep.csv")
    expected = {(r, s) for r in spec["main_sweep"]["relative_tolerances"]
                for s in spec["main_sweep"]["max_steps_s"]}
    assert len(main) == len(expected) == 40
    assert {(r["relative_tolerance"], r["max_step"]) for r in main} == expected
    assert len(atol) == 7
    assert {r["absolute_tolerance"] for r in atol} == set(spec["absolute_tolerance_sweep"]["absolute_tolerances"])
    for row in main + atol:
        assert row["analysis_revision"] == 4 and row["event_aligned_phase_points"] == 2049
        assert row["time_span_s"] == "[0.0, 10.0]"
        assert passes(row, spec["review_guards"]) == row["passes_review_guards"]
        if row["run_status"] == "completed":
            assert row["reference_transition_count"] == 16
            if not row["transition_signature_match"]:
                assert math.isnan(row["trajectory_rms_normalized"])
                assert math.isnan(row["maximum_event_time_error_s"])
        else:
            assert row["exception_type"] and row["exception_message"]
    dense = rows(artifacts / "retained_dense" / "dense_sweep.csv")
    grid = read_json(artifacts / "retained_dense" / "grid.json")
    assert len(dense) == 4945
    assert {(r["relative_tolerance"], r["max_step"]) for r in dense} == {
        (r, s) for r in grid["relative_tolerances"] for s in grid["max_steps_s"]}
    completed = [r for r in dense if r["run_status"] == "completed"]
    wrong = [r for r in completed if not r["transition_signature_match"]]
    assert len(completed) == 4681 and len(wrong) == 609
    selected = selected_row(dense)
    selection = read_json(artifacts / "selection.json")
    for k in ("relative_tolerance", "absolute_tolerance", "max_step"):
        assert selected[k] == selection["replay_config"][k]
    formal = formal_module()
    caches = {name: audit_cache(artifacts / selection[f"{name}_cache"], formal)
              for name in ("reference", "canonical", "selected")}
    ref = artifacts / selection["reference_cache"]
    can = artifacts / selection["canonical_cache"]
    scales = read_json(artifacts / "state_normalization_scales.json")
    assert scales == formal.state_scales(formal.load_trace(ref / "trace.npz"))
    recalculated = formal.compare_cache(can, ref, scales, spec["review_guards"])
    # A second, vectorized calculation checks the weighting and the placement of
    # the five-state mean without calling the formal comparison implementation.
    rcache, ccache = caches["reference"], caches["canonical"]
    squared_integral, independent_max = 0., 0.
    for i, seg in enumerate(rcache["segments"]):
        left = formal.unpack_segment_trace(rcache["payload"], i)
        right = formal.unpack_segment_trace(ccache["payload"], i)
        errors = np.stack([(right[k] - left[k]) / scales[k] for k in formal.STATE_KEYS])
        independent_max = max(independent_max, float(np.abs(errors).max()))
        squared_integral += float(np.trapezoid(np.mean(errors**2, axis=0), left["phase"])) * (seg["end_time_s"] - seg["start_time_s"])
    independent_rms = math.sqrt(squared_integral / 10.)
    assert close(independent_rms, recalculated["trajectory_rms_normalized"])
    assert close(independent_max, recalculated["trajectory_max_abs_normalized"])
    # Full native recomputation is available for reference/canonical, not every
    # archived formal cell. The latter are audited as retained numerical records.
    if record["formal_origin"].startswith("retained"):
        for key, value in recalculated.items():
            if isinstance(value, float) and key != "wall_time_s":
                assert close(value, summary["canonical"][key]), key
    replay = formal.compare_cache(artifacts / selection["selected_cache"], ref, scales, spec["review_guards"])
    for key, value in replay.items():
        if isinstance(value, float):
            assert close(value, selection["replay_metrics"][key]), key
    assert not replay["transition_signature_match"] and replay["transition_count"] == 12
    assert caches["reference"]["velocity_jump_count"] == caches["canonical"]["velocity_jump_count"] == 13
    assert [r["velocity_jump_above_1e_12"] for r in caches["reference"]["events"]] == [
        r["velocity_jump_above_1e_12"] for r in caches["canonical"]["events"]]
    values = {
        "run_id": record["run_id"], "formal_origin": record["formal_origin"],
        "formal_completed": sum(r["run_status"] == "completed" for r in main),
        "formal_passed": sum(r["passes_review_guards"] for r in main),
        "canonical": summary["canonical"], "guards": spec["review_guards"],
        "absolute_tolerance_sweep": atol, "state_scales": scales,
        "dense_total": len(dense), "dense_completed": len(completed),
        "dense_different_signature": len(wrong),
        "dense_gross_median": float(np.median([gross_rms(r) for r in wrong])),
        "dense_gross_p90": float(np.quantile([gross_rms(r) for r in wrong], .9)),
        "selected_config": selection["replay_config"],
        "selected_archived_gross_rms": gross_rms(selected),
        "selected_archived_native_point_count": int(selected["native_solver_point_count"]),
        "selected_replayed_gross_rms": gross_rms(replay),
        "selected_replay_metrics": replay,
        "independent_canonical_rms": independent_rms,
        "independent_canonical_maximum": independent_max,
        "event_audit": {k: {"events": v["events"], "velocity_jump_count": v["velocity_jump_count"]}
                        for k, v in caches.items()},
        "scope": "All tabulated guards recomputed; canonical metrics and three retained/replayed histories audited from native segment endpoints. Other individual dense/formal caches were not retained.",
    }
    return values, main, atol, dense, caches
