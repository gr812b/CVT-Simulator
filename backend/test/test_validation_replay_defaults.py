from __future__ import annotations

from app.database.validation import (
    DEFAULT_REPLAY_GAIN_NM_S_PER_RAD,
    VALIDATION_ABSOLUTE_TOLERANCE,
    VALIDATION_MAX_STEP_S,
    VALIDATION_RELATIVE_TOLERANCE,
    _apply_validation_integrator,
    _upgrade_workflow,
)


def _setup() -> dict:
    return {
        "scenario": {
            "initial_cvt_state": {
                "primary_angular_speed_rad_per_s": 10.0,
                "secondary_angular_speed_rad_per_s": 20.0,
                "belt_speed_m_per_s": 1.0,
                "shift_position_m": 0.002,
                "shift_speed_m_per_s": 0.0,
            }
        },
        "execution": {
            "integrator": {
                "relative_tolerance": 1.0e-2,
                "absolute_tolerance": 1.0e-5,
                "max_step": 0.2,
            }
        },
    }


def test_validation_integrator_is_replay_safe_without_changing_global_defaults() -> None:
    source = _setup()
    upgraded = _apply_validation_integrator(source)

    assert source["execution"]["integrator"]["relative_tolerance"] == 1.0e-2
    assert (
        upgraded["execution"]["integrator"]["relative_tolerance"]
        == VALIDATION_RELATIVE_TOLERANCE
    )
    assert (
        upgraded["execution"]["integrator"]["absolute_tolerance"]
        == VALIDATION_ABSOLUTE_TOLERANCE
    )
    assert upgraded["execution"]["integrator"]["max_step"] == VALIDATION_MAX_STEP_S


def test_legacy_speed_tracker_workspace_migrates_to_replay() -> None:
    workflow = _upgrade_workflow(
        {
            "primaryMode": "track_measured_speed",
            "secondaryMode": "physical",
            "axialMode": "track_measured_position",
            "speedTracking": {
                "proportionalGainNmSPerRad": 375.0,
                "torqueLimitNm": 30.0,
            },
            "axialTracking": {"forceLimitN": 1000.0},
        },
        _setup(),
    )

    assert workflow["primaryMode"] == "replay_measured_speed"
    assert workflow["secondaryMode"] == "physical"
    assert workflow["speedReplay"]["trackingGainNmSPerRad"] == 375.0
    assert workflow["validationIntegrator"] == {
        "relativeTolerance": VALIDATION_RELATIVE_TOLERANCE,
        "absoluteTolerance": VALIDATION_ABSOLUTE_TOLERANCE,
        "maxStepS": VALIDATION_MAX_STEP_S,
    }
    assert "speedTracking" not in workflow
    assert "axialMode" not in workflow
    assert "axialTracking" not in workflow


def test_invalid_legacy_gain_falls_back_to_audited_default() -> None:
    workflow = _upgrade_workflow(
        {"speedTracking": {"proportionalGainNmSPerRad": None}},
        _setup(),
    )
    assert workflow["speedReplay"]["trackingGainNmSPerRad"] == DEFAULT_REPLAY_GAIN_NM_S_PER_RAD
    assert workflow["rpmMeasurementDefaults"]["primary"]["replaySampleIntervalS"] == 0.01
    assert workflow["rpmMeasurementDefaults"]["secondary"]["replaySampleIntervalS"] == 0.01
