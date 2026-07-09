"""Seed data for local development and tests.

The seed set is deliberately small: it provides a few Baja institutions, one
public demo account, and a resolved Baja baseline split into the new database
objects. It is not endpoint wiring; it only exercises the persistence model.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.hashing import canonical_json_hash
from app.database.models import (
    Account,
    AccountInstitutionAffiliation,
    AccountUser,
    CVTDesign,
    CVTDesignVersion,
    Engine,
    EngineVersion,
    ExecutionPreset,
    Institution,
    LoadCase,
    OutputSystem,
    OutputSystemVersion,
    Tune,
    User,
    VehicleAssembly,
    VehicleAssemblyVersion,
)

JsonDict = dict[str, Any]

SEED_USER_ID = "00000000-0000-4000-8000-000000000001"
SEED_ACCOUNT_ID = "00000000-0000-4000-8000-000000000002"
SEED_ENGINE_ID = "00000000-0000-4000-8000-000000000010"
SEED_ENGINE_VERSION_ID = "00000000-0000-4000-8000-000000000011"
SEED_CVT_ID = "00000000-0000-4000-8000-000000000020"
SEED_CVT_VERSION_ID = "00000000-0000-4000-8000-000000000021"
SEED_OUTPUT_ID = "00000000-0000-4000-8000-000000000030"
SEED_OUTPUT_VERSION_ID = "00000000-0000-4000-8000-000000000031"
SEED_ASSEMBLY_ID = "00000000-0000-4000-8000-000000000040"
SEED_ASSEMBLY_VERSION_ID = "00000000-0000-4000-8000-000000000041"
SEED_TUNE_ID = "00000000-0000-4000-8000-000000000050"
SEED_LOAD_CASE_ID = "00000000-0000-4000-8000-000000000060"
SEED_EXECUTION_PRESET_ID = "00000000-0000-4000-8000-000000000070"

INSTITUTION_SEEDS: tuple[dict[str, Any], ...] = (
    {
        "id": "00000000-0000-4000-8000-000000001001",
        "name": "McMaster University",
        "slug": "mcmaster-university",
        "country_code": "CA",
        "region": "Ontario",
        "website_url": "https://www.mcmaster.ca/",
        "email_domains": ["mcmaster.ca"],
        "aliases": ["McMaster Baja", "McMaster Baja Racing"],
    },
    {
        "id": "00000000-0000-4000-8000-000000001002",
        "name": "Cornell University",
        "slug": "cornell-university",
        "country_code": "US",
        "region": "New York",
        "website_url": "https://www.cornell.edu/",
        "email_domains": ["cornell.edu"],
        "aliases": ["Cornell Baja Racing"],
    },
    {
        "id": "00000000-0000-4000-8000-000000001003",
        "name": "Virginia Tech",
        "slug": "virginia-tech",
        "country_code": "US",
        "region": "Virginia",
        "website_url": "https://www.vt.edu/",
        "email_domains": ["vt.edu"],
        "aliases": ["VT Baja", "Virginia Tech Baja"],
    },
    {
        "id": "00000000-0000-4000-8000-000000001004",
        "name": "West Virginia University",
        "slug": "west-virginia-university",
        "country_code": "US",
        "region": "West Virginia",
        "website_url": "https://www.wvu.edu/",
        "email_domains": ["mail.wvu.edu", "wvu.edu"],
        "aliases": ["WVU Baja"],
    },
    {
        "id": "00000000-0000-4000-8000-000000001005",
        "name": "Rochester Institute of Technology",
        "slug": "rochester-institute-of-technology",
        "country_code": "US",
        "region": "New York",
        "website_url": "https://www.rit.edu/",
        "email_domains": ["rit.edu"],
        "aliases": ["RIT Baja"],
    },
)


def seed_database(session: Session, *, preset_path: Path | None = None) -> None:
    """Insert deterministic local-development seed rows if they do not exist."""

    _seed_institutions(session)
    if session.get(Account, SEED_ACCOUNT_ID) is not None:
        return

    preset = _load_baseline_preset(preset_path)
    split = split_simulation_case_for_database(preset["simulation_case"])

    user = User(
        id=SEED_USER_ID,
        email="demo@mcmaster-baja.example",
        display_name="Demo Baja User",
    )
    account = Account(id=SEED_ACCOUNT_ID, name="Demo Baja Workspace", tier="free")
    session.add_all(
        [user, account, AccountUser(account_id=account.id, user_id=user.id, role="owner")]
    )
    session.flush()

    mcmaster = session.scalar(select(Institution).where(Institution.slug == "mcmaster-university"))
    if mcmaster is not None:
        session.add(
            AccountInstitutionAffiliation(
                account_id=account.id,
                institution_id=mcmaster.id,
                affiliation_label="McMaster Baja Racing",
                affiliation_type="baja_team",
                verification_status="self_reported",
                is_public=True,
            )
        )

    engine = Engine(
        id=SEED_ENGINE_ID,
        account_id=account.id,
        name="Demo Briggs & Stratton 10 hp",
        slug="demo-briggs-10hp",
        description="Seeded full-throttle Baja engine boundary with input inertia.",
        visibility="public",
        gallery_listed=True,
        lifecycle_status="active",
        catalog_status="official",
        catalog_priority=100,
        is_default=True,
        source_label="Seeded Baja baseline",
        source_notes="Curated demo engine boundary; not manufacturer-certified data.",
        draft_payload=copy.deepcopy(split["input_boundary"]),
    )
    engine_version = EngineVersion(
        id=SEED_ENGINE_VERSION_ID,
        engine_id=engine.id,
        version_number=1,
        input_boundary=split["input_boundary"],
        summary=_engine_summary(split["input_boundary"]),
        payload_hash=canonical_json_hash(split["input_boundary"]),
        schema_version=1,
        payload_schema_name="cinder.input_boundary.full_throttle_torque_curve",
        payload_schema_version=1,
        validation_status="valid",
        validation_messages=[],
        created_by_user_id=user.id,
        release_notes="Initial seeded engine boundary.",
        visibility_at_release="public",
        attribution_institution_id=mcmaster.id if mcmaster is not None else None,
        attribution_label="McMaster Baja Racing" if mcmaster is not None else None,
    )
    session.add_all([engine, engine_version])
    session.flush()
    engine.released_version_id = engine_version.id

    cvt_design = CVTDesign(
        id=SEED_CVT_ID,
        account_id=account.id,
        name="Demo Baja Rubber V-Belt CVT",
        slug="demo-baja-rubber-v-belt-cvt",
        description="Seeded CVT hardware assembly with CVT-owned inertias only.",
        visibility="public",
        gallery_listed=True,
        lifecycle_status="active",
        catalog_status="seeded_example",
        catalog_priority=90,
        is_default=True,
        source_label="Seeded Baja baseline",
        source_notes="Example rubber V-belt CVT hardware for local development and onboarding.",
        draft_payload=copy.deepcopy(split["cinder_assembly"]),
    )
    cvt_version = CVTDesignVersion(
        id=SEED_CVT_VERSION_ID,
        cvt_design_id=cvt_design.id,
        version_number=1,
        cinder_assembly=split["cinder_assembly"],
        tuning_schema=split["tuning_schema"],
        summary=_cvt_summary(split["cinder_assembly"]),
        payload_hash=canonical_json_hash(split["cinder_assembly"]),
        schema_version=1,
        payload_schema_name="cinder.cvt_assembly",
        payload_schema_version=1,
        validation_status="valid",
        validation_messages=[],
        created_by_user_id=user.id,
        release_notes="Initial seeded CVT hardware.",
        visibility_at_release="public",
        attribution_institution_id=mcmaster.id if mcmaster is not None else None,
        attribution_label="McMaster Baja Racing" if mcmaster is not None else None,
    )
    session.add_all([cvt_design, cvt_version])
    session.flush()
    cvt_design.released_version_id = cvt_version.id

    output_system = OutputSystem(
        id=SEED_OUTPUT_ID,
        account_id=account.id,
        name="Demo Baja Locked Final Drive Vehicle",
        slug="demo-baja-locked-final-drive-vehicle",
        description="Seeded vehicle/output boundary with drivetrain inertia at secondary shaft.",
        visibility="public",
        gallery_listed=True,
        lifecycle_status="active",
        catalog_status="seeded_example",
        catalog_priority=80,
        is_default=True,
        source_label="Seeded Baja baseline",
        source_notes="Example locked final-drive Baja output system.",
        draft_payload=copy.deepcopy(split["output_boundary_template"]),
    )
    output_version = OutputSystemVersion(
        id=SEED_OUTPUT_VERSION_ID,
        output_system_id=output_system.id,
        version_number=1,
        output_boundary_template=split["output_boundary_template"],
        summary=_output_summary(split["output_boundary_template"]),
        payload_hash=canonical_json_hash(split["output_boundary_template"]),
        schema_version=1,
        payload_schema_name="cinder.output_boundary.locked_final_drive_vehicle",
        payload_schema_version=1,
        validation_status="valid",
        validation_messages=[],
        created_by_user_id=user.id,
        release_notes="Initial seeded output system.",
        visibility_at_release="public",
        attribution_institution_id=mcmaster.id if mcmaster is not None else None,
        attribution_label="McMaster Baja Racing" if mcmaster is not None else None,
    )
    session.add_all([output_system, output_version])
    session.flush()
    output_system.released_version_id = output_version.id

    vehicle_assembly = VehicleAssembly(
        id=SEED_ASSEMBLY_ID,
        account_id=account.id,
        name="Demo Baja Vehicle Assembly",
        slug="demo-baja-vehicle-assembly",
        description="Seeded assembly pinning engine, CVT, and output system versions.",
        visibility="public",
        gallery_listed=True,
        lifecycle_status="active",
        catalog_status="seeded_example",
        catalog_priority=70,
        is_default=True,
        source_label="Seeded Baja baseline",
        source_notes="Example vehicle assembly tying seeded engine, CVT, and output system together.",
        draft_payload={
            "engine_version_id": engine_version.id,
            "cvt_design_version_id": cvt_version.id,
            "output_system_version_id": output_version.id,
        },
    )
    assembly_payload = {
        "notes": "Seeded Baja baseline. Runs freeze the fully resolved CINDER case.",
        "default_tune_id": SEED_TUNE_ID,
        "default_load_case_id": SEED_LOAD_CASE_ID,
    }
    assembly_version = VehicleAssemblyVersion(
        id=SEED_ASSEMBLY_VERSION_ID,
        vehicle_assembly_id=vehicle_assembly.id,
        version_number=1,
        engine_version_id=engine_version.id,
        cvt_design_version_id=cvt_version.id,
        output_system_version_id=output_version.id,
        assembly_payload=assembly_payload,
        summary={"kind": "baja_baseline", "name": "Demo Baja Vehicle Assembly"},
        payload_hash=canonical_json_hash(assembly_payload),
        schema_version=1,
        payload_schema_name="cvt_simulator.vehicle_assembly",
        payload_schema_version=1,
        validation_status="valid",
        validation_messages=[],
        created_by_user_id=user.id,
        release_notes="Initial seeded vehicle assembly.",
        visibility_at_release="public",
        attribution_institution_id=mcmaster.id if mcmaster is not None else None,
        attribution_label="McMaster Baja Racing" if mcmaster is not None else None,
    )
    session.add_all([vehicle_assembly, assembly_version])
    session.flush()
    vehicle_assembly.released_version_id = assembly_version.id

    session.add_all(
        [
            Tune(
                id=SEED_TUNE_ID,
                account_id=account.id,
                vehicle_assembly_id=vehicle_assembly.id,
                cvt_design_id=cvt_design.id,
                name="Baseline tune",
                values=split["baseline_tune"],
                notes="Seeded knobs extracted from the baseline CVT assembly.",
            ),
            LoadCase(
                id=SEED_LOAD_CASE_ID,
                account_id=account.id,
                name="Flat launch",
                kind="launch",
                visibility="public",
                payload=split["load_case"],
            ),
            ExecutionPreset(
                id=SEED_EXECUTION_PRESET_ID,
                account_id=None,
                name="Default accurate simulation",
                kind="simulation",
                payload=split["execution"],
                is_system_default=True,
            ),
        ]
    )


def split_simulation_case_for_database(simulation_case: JsonDict) -> JsonDict:
    """Split a legacy/full CINDER document into V1 database-owned objects."""

    input_boundary = copy.deepcopy(simulation_case["input_boundary"])
    cinder_assembly = copy.deepcopy(simulation_case["assembly"])
    output_boundary = copy.deepcopy(simulation_case["output_boundary"])

    primary_inertias = cinder_assembly["inertias"]["primary"]
    secondary_inertias = cinder_assembly["inertias"]["secondary"]

    engine_inertia = primary_inertias.pop("engine_rotational_inertia_kg_m2", None)
    if engine_inertia is not None:
        input_boundary.setdefault("equivalent_rotational_inertia_kg_m2", engine_inertia)
    if "cvt_rotational_inertia_kg_m2" in primary_inertias:
        primary_inertias["rotating_hardware_inertia_kg_m2"] = primary_inertias.pop(
            "cvt_rotational_inertia_kg_m2"
        )

    gearbox_inertia = secondary_inertias.pop("gearbox_input_rotational_inertia_kg_m2", None)
    if gearbox_inertia is not None:
        output_boundary.setdefault("direct_secondary_shaft_inertia_kg_m2", gearbox_inertia)
    if "fixed_rotational_inertia_kg_m2" in secondary_inertias:
        secondary_inertias["fixed_rotating_hardware_inertia_kg_m2"] = secondary_inertias.pop(
            "fixed_rotational_inertia_kg_m2"
        )
    output_boundary.setdefault("drivetrain_loss_model", {"kind": "none"})

    baseline_tune = _extract_baseline_tune(cinder_assembly)
    return {
        "input_boundary": input_boundary,
        "cinder_assembly": cinder_assembly,
        "output_boundary_template": output_boundary,
        "tuning_schema": _baseline_tuning_schema(),
        "baseline_tune": baseline_tune,
        "load_case": {
            "scenario": copy.deepcopy(simulation_case["scenario"]),
            "output_boundary_overrides": {},
        },
        "execution": copy.deepcopy(simulation_case["execution"]),
    }


def _seed_institutions(session: Session) -> None:
    for payload in INSTITUTION_SEEDS:
        if session.get(Institution, payload["id"]) is None:
            session.add(Institution(institution_type="university", is_verified=False, **payload))


def _load_baseline_preset(preset_path: Path | None) -> JsonDict:
    path = (
        preset_path or Path(__file__).resolve().parents[2] / "presets" / "baja-launch-baseline.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _baseline_tuning_schema() -> JsonDict:
    return {
        "parameters": [
            {
                "key": "flyweight_mass_kg",
                "label": "Flyweight mass",
                "unit": "kg",
                "path": "/pulleys/input/components/0/flyweight_mass_kg",
                "default": 0.8,
                "min": 0.1,
                "max": 1.5,
            },
            {
                "key": "primary_spring_initial_compression_m",
                "label": "Primary spring initial compression",
                "unit": "m",
                "path": "/pulleys/input/components/1/initial_compression_m",
                "default": 0.1046145479692159,
                "min": 0.0,
                "max": 0.2,
            },
            {
                "key": "secondary_spring_initial_compression_m",
                "label": "Secondary spring initial compression",
                "unit": "m",
                "path": "/pulleys/output/components/0/initial_compression_m",
                "default": 0.11,
                "min": 0.0,
                "max": 0.2,
            },
            {
                "key": "secondary_initial_twist_rad",
                "label": "Secondary spring initial twist",
                "unit": "rad",
                "path": "/pulleys/output/components/1/initial_twist_rad",
                "default": 5.235987755982989,
                "min": 0.0,
                "max": 7.0,
            },
            {
                "key": "secondary_helix_angle_rad",
                "label": "Secondary helix angle",
                "unit": "rad",
                "path": (
                    "/pulleys/output/helical_coupling/profile/"
                    "circumferential_profile/segments/0/angle_rad"
                ),
                "default": 1.2217304763960306,
                "min": 0.1,
                "max": 1.4,
            },
        ]
    }


def _extract_baseline_tune(cinder_assembly: JsonDict) -> JsonDict:
    values: JsonDict = {}
    try:
        values["flyweight_mass_kg"] = cinder_assembly["pulleys"]["input"]["components"][0][
            "flyweight_mass_kg"
        ]
    except (KeyError, IndexError, TypeError):
        pass
    try:
        values["primary_spring_initial_compression_m"] = cinder_assembly["pulleys"]["input"][
            "components"
        ][1]["initial_compression_m"]
    except (KeyError, IndexError, TypeError):
        pass
    try:
        values["secondary_spring_initial_compression_m"] = cinder_assembly["pulleys"]["output"][
            "components"
        ][0]["initial_compression_m"]
    except (KeyError, IndexError, TypeError):
        pass
    try:
        values["secondary_initial_twist_rad"] = cinder_assembly["pulleys"]["output"]["components"][
            1
        ]["initial_twist_rad"]
    except (KeyError, IndexError, TypeError):
        pass
    try:
        values["secondary_helix_angle_rad"] = cinder_assembly["pulleys"]["output"][
            "helical_coupling"
        ]["profile"]["circumferential_profile"]["segments"][0]["angle_rad"]
    except (KeyError, IndexError, TypeError):
        pass
    return values


def _engine_summary(input_boundary: JsonDict) -> JsonDict:
    points = input_boundary.get("points", [])
    peak_torque = max((float(point["torque_Nm"]) for point in points), default=0.0)
    peak_power = max(
        (float(point["torque_Nm"]) * float(point["angular_speed_rad_per_s"]) for point in points),
        default=0.0,
    )
    return {"peak_torque_Nm": peak_torque, "peak_power_W": peak_power}


def _cvt_summary(cinder_assembly: JsonDict) -> JsonDict:
    geometry = cinder_assembly.get("geometry", {})
    return {
        "belt_outer_length_m": geometry.get("belt_outer_length_m"),
        "max_shift_m": geometry.get("max_shift_m"),
        "deadzone_shift_m": geometry.get("deadzone_shift_m"),
    }


def _output_summary(output_boundary: JsonDict) -> JsonDict:
    vehicle = output_boundary.get("vehicle", {})
    final_drive = output_boundary.get("final_drive", {})
    return {
        "mass_kg": vehicle.get("mass_kg"),
        "reduction_ratio": final_drive.get("reduction_ratio"),
        "wheel_radius_m": final_drive.get("wheel_radius_m"),
        "direct_secondary_shaft_inertia_kg_m2": output_boundary.get(
            "direct_secondary_shaft_inertia_kg_m2"
        ),
    }
