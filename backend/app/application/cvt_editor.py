"""Read-only CVT working-copy adapters over the existing CINDER/Tune pipeline."""

from copy import deepcopy

import numpy as np

from app.application.experiment_tuning import apply_values, parameters, tune_fields
from app.application.physical_contracts import GATEWAY, with_belt
from app.application.physical_library import _default_tuning_schema
from app.application.scene_mass import flyweight_tip_mass_kg
from app.application.tune_preview import build_tune_preview
from app.core.errors import ApiProblem
from app.schemas.cvt_editor import InitialTuneSurface
from app.schemas.physical_library import CvtData
from app.schemas.scene import FlyweightScene, MechanismPose, MechanismScene


def initial_parameters(cvt: CvtData):
    current = with_belt(cvt)
    params = parameters(current.assembly, _default_tuning_schema())
    keys = [param["key"] for param in params]
    if len(set(keys)) != len(keys):
        raise ApiProblem(
            422,
            "ambiguous_initial_tune",
            "This hardware has more than one mechanism using the same tune controls. "
            "Its saved values are retained, but the initial-tune editor cannot change them safely.",
        )
    return current, params


def initial_tune_surface(cvt: CvtData) -> InitialTuneSurface:
    _current, params = initial_parameters(cvt)
    return InitialTuneSurface(
        fields=tune_fields(params),
        values={param["key"]: deepcopy(param["default"]) for param in params},
    )


def apply_initial_tune(cvt: CvtData, values: dict) -> CvtData:
    current, params = initial_parameters(cvt)
    defaults = {param["key"]: param["default"] for param in params}
    # Untouched offsets/masses/profiles stay exactly as supplied by the working
    # copy. Only intentional Tune edits go through the shared applicator.
    changed = {
        key: value
        for key, value in values.items()
        if key not in defaults or value != defaults[key]
    }
    apply_values(current.assembly, params, changed)
    return CvtData.model_validate(current.model_dump())


def pulley_preview(geometry: dict):
    return GATEWAY.scene_preview(deepcopy(geometry), frame_count=65)


def mechanism_preview(cvt: CvtData):
    """Hardware-only primary mechanism preview; never solve roller contact."""
    from cinder.contracts.document import _decode_flyweight_geometry

    current = with_belt(cvt)
    assembly = current.assembly
    GATEWAY.validate_assembly_shape(assembly)
    preview = GATEWAY.scene_preview(assembly["geometry"], frame_count=1)
    primary_components = assembly["pulleys"]["primary"]["components"]
    secondary_components = assembly["pulleys"]["secondary"]["components"]
    flyweights = [
        component
        for component in primary_components
        if component["kind"] == "fixed_pivot_roller_flyweight"
    ]
    if len(flyweights) > 1:
        raise ValueError(
            "The hardware preview supports one fixed-pivot mechanism per primary."
        )
    primary = None
    if flyweights:
        component = flyweights[0]
        spec = _decode_flyweight_geometry(component["geometry"])
        coordinates = np.linspace(spec.ramp_profile.x_min, spec.ramp_profile.x_max, 81)
        primary = FlyweightScene(
            count=component["mass_geometry"]["number_of_flyweights"],
            tip_mass_per_flyweight_kg=flyweight_tip_mass_kg(component),
            pivot_m=(spec.pivot_axial_position, spec.pivot_radius),
            roller_radius_m=spec.roller_radius,
            roller_side_sign=spec.roller_side_sign,
            ramp_points_m=[
                (
                    spec.ramp_reference_axial_position
                    + spec.ramp_axial_direction * float(coordinate),
                    spec.ramp_reference_radius
                    + spec.ramp_profile.evaluate(float(coordinate)).value,
                )
                for coordinate in coordinates
            ],
        )
    preview.geometry.mechanisms = MechanismScene(
        primary=primary,
        primary_has_spring=any(
            component["kind"] == "axial_spring" for component in primary_components
        ),
        secondary_has_spring=any(
            component["kind"] == "axial_spring" for component in secondary_components
        ),
        secondary_helix_points_m=[],
        poses=[
            MechanismPose(
                shift_m=0,
                primary_contact_m=None,
                primary_normal_axial_radial=None,
                primary_roller_m=None,
                primary_ramp_shift_m=0,
                secondary_axial_position_m=0,
                secondary_angle_rad=0,
                secondary_helix_dtheta_dx=None,
            )
        ],
    )
    return preview


def initial_tune_preview(cvt: CvtData, values: dict):
    # Initial Tune uses the normal sampled contact preview. Full construction
    # validation still happens only on the subsequent physical Save/run.
    return build_tune_preview(GATEWAY, apply_initial_tune(cvt, values).assembly)
