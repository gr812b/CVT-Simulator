"""Unit metadata is additive, dimension checked, and independent of SI documents."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.schemas.unit_preferences import UNIT_CHOICES, UnitPreferences


def test_defaults_leave_inertia_si_and_preserve_legacy_keys():
    prefs = UnitPreferences().model_dump()
    assert prefs["hardware_length"] == "in"
    assert prefs["component_mass"] == "g"
    assert prefs["course_length"] == "m"
    assert prefs["output_speed"] == "km/h"
    assert prefs["quantity_units"] == {}


def test_every_advertised_unit_is_accepted_in_its_own_dimension():
    for scope, dimensions in UNIT_CHOICES.items():
        for dimension, units in dimensions.items():
            for unit in units:
                prefs = UnitPreferences(quantity_units={scope: {dimension: unit}})
                assert prefs.quantity_units[scope][dimension] == unit


@pytest.mark.parametrize("value", [
    {"hardware": {"inertia": "lbf·in"}},
    {"hardware": {"torsional_stiffness": "N/mm"}},
    {"output": {"area": "m"}},
    {"course": {"not_a_dimension": "m"}},
    {"other_scope": {"area": "m²"}},
])
def test_mismatched_dimensions_and_unknown_preferences_fail_closed(value):
    with pytest.raises(ValidationError):
        UnitPreferences(quantity_units=value)


def test_partial_legacy_patch_keeps_added_preferences_without_mutation():
    previous = UnitPreferences(quantity_units={"hardware": {"inertia": "g·mm²"}}).model_dump()
    before = deepcopy(previous)
    result = UnitPreferences(hardware_length="mm").apply_to(previous)
    assert result["hardware_length"] == "mm"
    assert result["quantity_units"] == previous["quantity_units"]
    assert previous == before
    cleared = UnitPreferences(quantity_units={}).apply_to(result)
    assert cleared["quantity_units"] == {}
    assert cleared["hardware_length"] == "mm"


def test_scopes_and_user_preferences_have_independent_defaults():
    first = UnitPreferences(quantity_units={"hardware": {"area": "in²"}, "output": {"area": "ft²"}})
    second = UnitPreferences()
    assert second.quantity_units == {}
    assert first.quantity_units["hardware"]["area"] != first.quantity_units["output"]["area"]
