"""Tip-mass scene metadata against real CINDER mass builders and contact paths."""

from copy import deepcopy
from dataclasses import replace

import pytest

from cinder.model.cvt.actuation.fixed_pivot_flyweight import FlyweightMassGeometry

from app.application.cinder_gateway import CinderGateway
from app.application.physical_contracts import assembly_with_matching_belt, baseline_case
from app.application.scene_mass import flyweight_tip_mass_kg
from app.application.tune_preview import build_tune_preview
from app.schemas.scene import FlyweightScene, ScenePreview, TuneScenePreview

BODY_MASS_KG = 0.013646


@pytest.fixture(scope="module")
def baseline():
    return assembly_with_matching_belt(baseline_case()["assembly"])


def flyweight(assembly):
    return next(
        component
        for component in assembly["pulleys"]["primary"]["components"]
        if component["kind"] == "fixed_pivot_roller_flyweight"
    )


def encoded_mass(mass):
    """Use CINDER's generated moments; only map its public attributes to JSON."""
    return {
        "number_of_flyweights": mass.number_of_flyweights,
        "mass_per_flyweight_kg": mass.mass_per_flyweight,
        "first_moment_u_kg_m": mass.first_moment_u,
        "first_moment_v_kg_m": mass.first_moment_v,
        "second_moment_u_kg_m2": mass.second_moment_u,
        "second_moment_v_kg_m2": mass.second_moment_v,
        "product_moment_uv_kg_m2": mass.product_moment_uv,
        "second_moment_z_kg_m2": mass.second_moment_z,
    }


def uniform_arm(assembly, tip_mass):
    return FlyweightMassGeometry.uniform_arm_with_end_mass(
        number_of_flyweights=3,
        arm_length=flyweight(assembly)["geometry"]["arm_length_m"],
        arm_mass_per_flyweight=BODY_MASS_KG,
        end_mass_per_flyweight=tip_mass,
    )


@pytest.fixture(params=["tune_preview", "tune_scene", "assembly_scene"])
def scene_builder(request):
    gateway = CinderGateway()
    if request.param == "tune_preview":
        return lambda assembly: build_tune_preview(gateway, assembly)
    return getattr(gateway, request.param)


def test_delivered_baseline_reports_replaceable_tip_not_body_or_set_total(baseline):
    component = flyweight(baseline)
    assert component["mass_geometry"]["number_of_flyweights"] == 3
    assert component["mass_geometry"]["mass_per_flyweight_kg"] == pytest.approx(0.25 + BODY_MASS_KG)
    assert flyweight_tip_mass_kg(component) == pytest.approx(0.25)


def test_tip_mass_changes_scene_metadata_without_moving_mechanisms(baseline, scene_builder):
    reference_geometry = None
    for tip_mass in (0.15, 0.30, 0.45, 0.50):
        assembly = deepcopy(baseline)
        flyweight(assembly)["mass_geometry"] = encoded_mass(uniform_arm(assembly, tip_mass))
        unchanged_input = deepcopy(assembly)
        response = scene_builder(assembly)
        primary = response.geometry.mechanisms.primary
        assert primary.count == 3
        assert primary.tip_mass_per_flyweight_kg == pytest.approx(tip_mass)
        assert any(pose.primary_roller_m is not None for pose in response.geometry.mechanisms.poses)
        if isinstance(response, TuneScenePreview):
            assert response.validation["is_valid"]
        assert assembly == unchanged_input
        # Includes exact roller centres, ramp/contact points, pose angles, radii
        # and belt paths. Only the mass used for the illustration may differ.
        geometry = response.model_dump()
        geometry["geometry"]["mechanisms"]["primary"].pop("tip_mass_per_flyweight_kg")
        if reference_geometry is None:
            reference_geometry = geometry
        else:
            assert geometry == reference_geometry


def test_nonuniform_mass_does_not_claim_a_tip_mass_in_any_scene(baseline, scene_builder):
    assembly = deepcopy(baseline)
    # A concentrated mass halfway along the arm is physically valid, but is
    # not the uniform body plus roller-station mass used by the illustration.
    station = flyweight(assembly)["geometry"]["arm_length_m"] / 2
    mass = FlyweightMassGeometry(
        number_of_flyweights=3,
        mass_per_flyweight=0.3,
        first_moment_u=0.3 * station,
        first_moment_v=0,
        second_moment_u=0.3 * station**2,
        second_moment_v=0,
    )
    flyweight(assembly)["mass_geometry"] = encoded_mass(mass)
    response = scene_builder(assembly)
    assert response.geometry.mechanisms.primary.tip_mass_per_flyweight_kg is None
    assert response.geometry.mechanisms.primary.count == 3
    assert any(pose.primary_roller_m is not None for pose in response.geometry.mechanisms.poses)


def test_transverse_mass_distribution_retains_unscaled_fallback(baseline):
    assembly = deepcopy(baseline)
    # Preserve the generated axial moments but give the body a finite spread
    # perpendicular to the arm; this is outside the simple illustration model.
    mass = replace(uniform_arm(assembly, 0.3), second_moment_v=1e-6)
    flyweight(assembly)["mass_geometry"] = encoded_mass(mass)
    assert flyweight_tip_mass_kg(flyweight(assembly)) is None


def test_retained_scene_without_mass_field_remains_readable(baseline):
    response = CinderGateway().tune_scene(baseline)
    legacy = response.model_dump(mode="json")
    primary = legacy["geometry"]["mechanisms"]["primary"]
    primary.pop("tip_mass_per_flyweight_kg")
    assert FlyweightScene.model_validate(primary).tip_mass_per_flyweight_kg is None
    recovered = ScenePreview.model_validate(legacy)
    assert recovered.geometry.mechanisms.primary.tip_mass_per_flyweight_kg is None
    assert recovered.geometry.mechanisms.poses == response.geometry.mechanisms.poses
    assert recovered.frames == response.frames
