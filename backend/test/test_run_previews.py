"""Focused checks for durable run preview generation."""

from __future__ import annotations

from app.database.run_previews import DEFAULT_PREVIEW_PROFILE, build_run_preview


def test_preview_downsamples_uniformly_and_preserves_endpoints() -> None:
    result = {
        "report_table": {
            "axis_key": "time_s",
            "row_count": 1001,
            "columns": [
                {"key": "time_s", "label": "time", "values": list(range(1001))},
                {"key": "state.shift_position", "values": [value * 2 for value in range(1001)]},
                {"key": "ignored.debug", "values": list(range(1001))},
            ],
        }
    }

    preview = build_run_preview(result, source_result_hash="abc123")

    assert preview["profile_name"] == DEFAULT_PREVIEW_PROFILE.name
    assert preview["profile_version"] == DEFAULT_PREVIEW_PROFILE.version
    assert preview["source_result_hash"] == "abc123"
    assert preview["original_row_count"] == 1001
    assert preview["preview_row_count"] <= DEFAULT_PREVIEW_PROFILE.max_points
    assert preview["sampled_indices"][0] == 0
    assert preview["sampled_indices"][-1] == 1000
    keys = {column["key"] for column in preview["columns"]}
    assert "time_s" in keys
    assert "state.shift_position" in keys
    assert "ignored.debug" not in keys

    by_key = {column["key"]: column for column in preview["columns"]}
    expected_time_values = preview["sampled_indices"]
    assert by_key["time_s"]["values"] == expected_time_values
    assert by_key["state.shift_position"]["values"] == [index * 2 for index in expected_time_values]


def test_preview_keeps_small_tables_without_compression() -> None:
    result = {
        "report_table": {
            "axis_key": "time_s",
            "row_count": 3,
            "columns": [
                {"key": "time_s", "values": [0.0, 0.1, 0.2]},
                {"key": "vehicle.speed", "values": [0.0, 1.0, 2.0]},
            ],
        }
    }

    preview = build_run_preview(result)

    assert preview["original_row_count"] == 3
    assert preview["preview_row_count"] == 3
    assert preview["sampled_indices"] == [0, 1, 2]
