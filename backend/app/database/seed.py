"""Seed data for local development and tests.

The seed set is deliberately small: it provides a few Baja institutions, one
public demo account, and a resolved Baja baseline split into the new database
objects. It is not endpoint wiring; it only exercises the persistence model.
"""

from __future__ import annotations

import copy
import json
from math import radians
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
SEED_OUTPUT_LIGHT_ID = "00000000-0000-4000-8000-000000000032"
SEED_OUTPUT_LIGHT_VERSION_ID = "00000000-0000-4000-8000-000000000033"
SEED_ASSEMBLY_ID = "00000000-0000-4000-8000-000000000040"
SEED_ASSEMBLY_VERSION_ID = "00000000-0000-4000-8000-000000000041"
SEED_ASSEMBLY_LIGHT_ID = "00000000-0000-4000-8000-000000000042"
SEED_ASSEMBLY_LIGHT_VERSION_ID = "00000000-0000-4000-8000-000000000043"
SEED_TUNE_ID = "00000000-0000-4000-8000-000000000050"
SEED_TUNE_LIGHT_ID = "00000000-0000-4000-8000-000000000051"
SEED_LOAD_CASE_ID = "00000000-0000-4000-8000-000000000060"
SEED_LOAD_CASE_HILL_20_ID = "00000000-0000-4000-8000-000000000061"
SEED_LOAD_CASE_FLAT_THEN_HILL_20_ID = "00000000-0000-4000-8000-000000000062"
SEED_EXECUTION_PRESET_ID = "00000000-0000-4000-8000-000000000070"

POUND_TO_KG = 0.45359237
SEED_HEAVY_VEHICLE_MASS_KG = 500.0 * POUND_TO_KG
SEED_LIGHT_VEHICLE_MASS_KG = 400.0 * POUND_TO_KG
SEED_HILL_20_DEG_RAD = radians(20.0)
SEED_HILL_30_DEG_RAD = radians(30.0)
SEED_FLAT_RUNUP_DISTANCE_M = 90.0

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

    preset = _load_baseline_preset(preset_path)
    split = split_simulation_case_for_database(preset["simulation_case"])

    if session.get(Account, SEED_ACCOUNT_ID) is not None:
        _refresh_seed_tuning_surface(session, split)
        _refresh_seed_run_setups(session, split)
        return

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

    heavy_output_boundary = _with_vehicle_mass(
        split["output_boundary_template"], SEED_HEAVY_VEHICLE_MASS_KG
    )
    light_output_boundary = _with_vehicle_mass(
        split["output_boundary_template"], SEED_LIGHT_VEHICLE_MASS_KG
    )

    output_system = OutputSystem(
        id=SEED_OUTPUT_ID,
        account_id=account.id,
        name="Demo Baja 500 lb Locked Final Drive Vehicle",
        slug="demo-baja-500lb-locked-final-drive-vehicle",
        description="Seeded 500 lb Baja vehicle/output boundary with drivetrain inertia at secondary shaft.",
        visibility="public",
        gallery_listed=True,
        lifecycle_status="active",
        catalog_status="seeded_example",
        catalog_priority=80,
        is_default=True,
        source_label="Seeded Baja baseline",
        source_notes="Example 500 lb locked final-drive Baja output system.",
        draft_payload=copy.deepcopy(heavy_output_boundary),
    )
    output_version = OutputSystemVersion(
        id=SEED_OUTPUT_VERSION_ID,
        output_system_id=output_system.id,
        version_number=1,
        output_boundary_template=heavy_output_boundary,
        summary=_output_summary(heavy_output_boundary),
        payload_hash=canonical_json_hash(heavy_output_boundary),
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
        name="Demo Baja 500 lb Vehicle Assembly",
        slug="demo-baja-500lb-vehicle-assembly",
        description="Seeded 500 lb Baja assembly pinning engine, CVT, and output system versions.",
        visibility="public",
        gallery_listed=True,
        lifecycle_status="active",
        catalog_status="seeded_example",
        catalog_priority=70,
        is_default=True,
        source_label="Seeded Baja baseline",
        source_notes="Example 500 lb vehicle assembly tying seeded engine, CVT, and output system together.",
        draft_payload={
            "engine_version_id": engine_version.id,
            "cvt_design_version_id": cvt_version.id,
            "output_system_version_id": output_version.id,
        },
    )
    assembly_payload = {
        "notes": "Seeded Baja 500 lb baseline. Runs freeze the fully resolved CINDER case.",
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
        summary={
            "kind": "baja_baseline",
            "name": "Demo Baja 500 lb Vehicle Assembly",
            "vehicle_mass_kg": SEED_HEAVY_VEHICLE_MASS_KG,
            "vehicle_mass_lb": 500.0,
        },
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

    light_output_system = OutputSystem(
        id=SEED_OUTPUT_LIGHT_ID,
        account_id=account.id,
        name="Demo Baja 400 lb Locked Final Drive Vehicle",
        slug="demo-baja-400lb-locked-final-drive-vehicle",
        description="Seeded 400 lb Baja vehicle/output boundary using the same engine and CVT hardware.",
        visibility="public",
        gallery_listed=True,
        lifecycle_status="active",
        catalog_status="seeded_example",
        catalog_priority=75,
        is_default=False,
        source_label="Seeded Baja baseline",
        source_notes="Example 400 lb locked final-drive Baja output system for mass sensitivity checks.",
        draft_payload=copy.deepcopy(light_output_boundary),
    )
    light_output_version = OutputSystemVersion(
        id=SEED_OUTPUT_LIGHT_VERSION_ID,
        output_system_id=light_output_system.id,
        version_number=1,
        output_boundary_template=light_output_boundary,
        summary=_output_summary(light_output_boundary),
        payload_hash=canonical_json_hash(light_output_boundary),
        schema_version=1,
        payload_schema_name="cinder.output_boundary.locked_final_drive_vehicle",
        payload_schema_version=1,
        validation_status="valid",
        validation_messages=[],
        created_by_user_id=user.id,
        release_notes="Initial seeded 400 lb output system.",
        visibility_at_release="public",
        attribution_institution_id=mcmaster.id if mcmaster is not None else None,
        attribution_label="McMaster Baja Racing" if mcmaster is not None else None,
    )
    session.add_all([light_output_system, light_output_version])
    session.flush()
    light_output_system.released_version_id = light_output_version.id

    light_vehicle_assembly = VehicleAssembly(
        id=SEED_ASSEMBLY_LIGHT_ID,
        account_id=account.id,
        name="Demo Baja 400 lb Vehicle Assembly",
        slug="demo-baja-400lb-vehicle-assembly",
        description="Seeded 400 lb Baja assembly using the same engine and CVT with a lighter vehicle boundary.",
        visibility="public",
        gallery_listed=True,
        lifecycle_status="active",
        catalog_status="seeded_example",
        catalog_priority=65,
        is_default=False,
        source_label="Seeded Baja baseline",
        source_notes="Example 400 lb vehicle assembly tying seeded engine, CVT, and lighter output system together.",
        draft_payload={
            "engine_version_id": engine_version.id,
            "cvt_design_version_id": cvt_version.id,
            "output_system_version_id": light_output_version.id,
        },
    )
    light_assembly_payload = {
        "notes": "Seeded Baja 400 lb baseline. Runs freeze the fully resolved CINDER case.",
        "default_tune_id": SEED_TUNE_LIGHT_ID,
        "default_load_case_id": SEED_LOAD_CASE_ID,
    }
    light_assembly_version = VehicleAssemblyVersion(
        id=SEED_ASSEMBLY_LIGHT_VERSION_ID,
        vehicle_assembly_id=light_vehicle_assembly.id,
        version_number=1,
        engine_version_id=engine_version.id,
        cvt_design_version_id=cvt_version.id,
        output_system_version_id=light_output_version.id,
        assembly_payload=light_assembly_payload,
        summary={
            "kind": "baja_baseline",
            "name": "Demo Baja 400 lb Vehicle Assembly",
            "vehicle_mass_kg": SEED_LIGHT_VEHICLE_MASS_KG,
            "vehicle_mass_lb": 400.0,
        },
        payload_hash=canonical_json_hash(light_assembly_payload),
        schema_version=1,
        payload_schema_name="cvt_simulator.vehicle_assembly",
        payload_schema_version=1,
        validation_status="valid",
        validation_messages=[],
        created_by_user_id=user.id,
        release_notes="Initial seeded 400 lb vehicle assembly.",
        visibility_at_release="public",
        attribution_institution_id=mcmaster.id if mcmaster is not None else None,
        attribution_label="McMaster Baja Racing" if mcmaster is not None else None,
    )
    session.add_all([light_vehicle_assembly, light_assembly_version])
    session.flush()
    light_vehicle_assembly.released_version_id = light_assembly_version.id

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
            Tune(
                id=SEED_TUNE_LIGHT_ID,
                account_id=account.id,
                vehicle_assembly_id=light_vehicle_assembly.id,
                cvt_design_id=cvt_design.id,
                name="Baseline tune — 400 lb vehicle",
                values=copy.deepcopy(split["baseline_tune"]),
                notes="Same seeded CVT tune, associated with the 400 lb vehicle assembly.",
            ),
            LoadCase(
                id=SEED_LOAD_CASE_ID,
                account_id=account.id,
                name="Flat launch",
                kind="launch",
                visibility="public",
                payload=_load_case_payload(split["load_case"], grade_angle_rad=0.0),
            ),
            LoadCase(
                id=SEED_LOAD_CASE_HILL_20_ID,
                account_id=account.id,
                name="20° hill launch",
                kind="hill_launch",
                visibility="public",
                payload=_load_case_payload(
                    split["load_case"], grade_angle_rad=SEED_HILL_20_DEG_RAD
                ),
            ),
            LoadCase(
                id=SEED_LOAD_CASE_FLAT_THEN_HILL_20_ID,
                account_id=account.id,
                name="90 m flat into 30° hill",
                kind="route_launch",
                visibility="public",
                payload=_load_case_payload(
                    split["load_case"],
                    road_profile=_flat_then_hill_road_profile(),
                    metadata={
                        "route_intent": "distance_flat_then_30deg_hill",
                        "flat_segment_distance_m": SEED_FLAT_RUNUP_DISTANCE_M,
                        "hill_grade_angle_rad": SEED_HILL_30_DEG_RAD,
                        "description": (
                            "Executable route profile: flat launch until 90 m vehicle distance, "
                            "then a 30 degree hill."
                        ),
                    },
                ),
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


def _refresh_seed_tuning_surface(session: Session, split: JsonDict) -> None:
    """Patch existing local demo seed rows with newly exposed tune keys.

    This is development/test seed maintenance only. It avoids stale local SQLite
    databases silently missing tune inputs after the frontend tuning surface is
    expanded, while preserving any values the tester has already changed.
    """

    cvt_version = session.get(CVTDesignVersion, SEED_CVT_VERSION_ID)
    if cvt_version is not None:
        cvt_version.tuning_schema = copy.deepcopy(split["tuning_schema"])

    tune = session.get(Tune, SEED_TUNE_ID)
    if tune is not None:
        merged_values = copy.deepcopy(split["baseline_tune"])
        merged_values.update(copy.deepcopy(tune.values or {}))
        tune.values = merged_values


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


def _refresh_seed_run_setups(session: Session, split: JsonDict) -> None:
    """Upsert the expanded local demo vehicle and load-case seed set.

    This is development/test seed maintenance only. Rerunning
    ``python -m app.scripts.init_database`` should patch a stale local SQLite DB
    with the current demo run-setup options without forcing the developer to
    delete the database manually.
    """

    account = session.get(Account, SEED_ACCOUNT_ID)
    user = session.get(User, SEED_USER_ID)
    if account is None:
        return

    mcmaster = session.scalar(select(Institution).where(Institution.slug == "mcmaster-university"))
    heavy_output_boundary = _with_vehicle_mass(
        split["output_boundary_template"], SEED_HEAVY_VEHICLE_MASS_KG
    )
    light_output_boundary = _with_vehicle_mass(
        split["output_boundary_template"], SEED_LIGHT_VEHICLE_MASS_KG
    )

    _upsert_output_system_seed(
        session,
        account_id=account.id,
        user_id=user.id if user is not None else None,
        institution_id=mcmaster.id if mcmaster is not None else None,
        object_id=SEED_OUTPUT_ID,
        version_id=SEED_OUTPUT_VERSION_ID,
        name="Demo Baja 500 lb Locked Final Drive Vehicle",
        slug="demo-baja-500lb-locked-final-drive-vehicle",
        description="Seeded 500 lb Baja vehicle/output boundary with drivetrain inertia at secondary shaft.",
        catalog_priority=80,
        is_default=True,
        source_notes="Example 500 lb locked final-drive Baja output system.",
        release_notes="Initial seeded 500 lb output system.",
        output_boundary=heavy_output_boundary,
    )
    _upsert_output_system_seed(
        session,
        account_id=account.id,
        user_id=user.id if user is not None else None,
        institution_id=mcmaster.id if mcmaster is not None else None,
        object_id=SEED_OUTPUT_LIGHT_ID,
        version_id=SEED_OUTPUT_LIGHT_VERSION_ID,
        name="Demo Baja 400 lb Locked Final Drive Vehicle",
        slug="demo-baja-400lb-locked-final-drive-vehicle",
        description="Seeded 400 lb Baja vehicle/output boundary using the same engine and CVT hardware.",
        catalog_priority=75,
        is_default=False,
        source_notes="Example 400 lb locked final-drive Baja output system for mass sensitivity checks.",
        release_notes="Initial seeded 400 lb output system.",
        output_boundary=light_output_boundary,
    )

    _upsert_vehicle_assembly_seed(
        session,
        account_id=account.id,
        user_id=user.id if user is not None else None,
        institution_id=mcmaster.id if mcmaster is not None else None,
        object_id=SEED_ASSEMBLY_ID,
        version_id=SEED_ASSEMBLY_VERSION_ID,
        output_version_id=SEED_OUTPUT_VERSION_ID,
        default_tune_id=SEED_TUNE_ID,
        name="Demo Baja 500 lb Vehicle Assembly",
        slug="demo-baja-500lb-vehicle-assembly",
        description="Seeded 500 lb Baja assembly pinning engine, CVT, and output system versions.",
        catalog_priority=70,
        is_default=True,
        vehicle_mass_kg=SEED_HEAVY_VEHICLE_MASS_KG,
        vehicle_mass_lb=500.0,
    )
    _upsert_vehicle_assembly_seed(
        session,
        account_id=account.id,
        user_id=user.id if user is not None else None,
        institution_id=mcmaster.id if mcmaster is not None else None,
        object_id=SEED_ASSEMBLY_LIGHT_ID,
        version_id=SEED_ASSEMBLY_LIGHT_VERSION_ID,
        output_version_id=SEED_OUTPUT_LIGHT_VERSION_ID,
        default_tune_id=SEED_TUNE_LIGHT_ID,
        name="Demo Baja 400 lb Vehicle Assembly",
        slug="demo-baja-400lb-vehicle-assembly",
        description="Seeded 400 lb Baja assembly using the same engine and CVT with a lighter vehicle boundary.",
        catalog_priority=65,
        is_default=False,
        vehicle_mass_kg=SEED_LIGHT_VEHICLE_MASS_KG,
        vehicle_mass_lb=400.0,
    )

    _upsert_tune_seed(
        session,
        tune_id=SEED_TUNE_LIGHT_ID,
        account_id=account.id,
        vehicle_assembly_id=SEED_ASSEMBLY_LIGHT_ID,
        cvt_design_id=SEED_CVT_ID,
        name="Baseline tune — 400 lb vehicle",
        values=split["baseline_tune"],
        notes="Same seeded CVT tune, associated with the 400 lb vehicle assembly.",
    )

    _upsert_load_case_seed(
        session,
        load_case_id=SEED_LOAD_CASE_ID,
        account_id=account.id,
        name="Flat launch",
        kind="launch",
        payload=_load_case_payload(split["load_case"], grade_angle_rad=0.0),
    )
    _upsert_load_case_seed(
        session,
        load_case_id=SEED_LOAD_CASE_HILL_20_ID,
        account_id=account.id,
        name="20° hill launch",
        kind="hill_launch",
        payload=_load_case_payload(split["load_case"], grade_angle_rad=SEED_HILL_20_DEG_RAD),
    )
    _upsert_load_case_seed(
        session,
        load_case_id=SEED_LOAD_CASE_FLAT_THEN_HILL_20_ID,
        account_id=account.id,
        name="90 m flat into 30° hill",
        kind="route_launch",
        payload=_load_case_payload(
            split["load_case"],
            road_profile=_flat_then_hill_road_profile(),
            metadata={
                "route_intent": "distance_flat_then_30deg_hill",
                "flat_segment_distance_m": SEED_FLAT_RUNUP_DISTANCE_M,
                "hill_grade_angle_rad": SEED_HILL_30_DEG_RAD,
                "description": (
                    "Executable route profile: flat launch until 90 m vehicle distance, "
                    "then a 30 degree hill."
                ),
            },
        ),
    )


def _upsert_output_system_seed(
    session: Session,
    *,
    account_id: str,
    user_id: str | None,
    institution_id: str | None,
    object_id: str,
    version_id: str,
    name: str,
    slug: str,
    description: str,
    catalog_priority: int,
    is_default: bool,
    source_notes: str,
    release_notes: str,
    output_boundary: JsonDict,
) -> None:
    output_system = session.get(OutputSystem, object_id)
    if output_system is None:
        output_system = OutputSystem(id=object_id, account_id=account_id)
        session.add(output_system)
    output_system.name = name
    output_system.slug = slug
    output_system.description = description
    output_system.visibility = "public"
    output_system.gallery_listed = True
    output_system.lifecycle_status = "active"
    output_system.catalog_status = "seeded_example"
    output_system.catalog_priority = catalog_priority
    output_system.is_default = is_default
    output_system.source_label = "Seeded Baja baseline"
    output_system.source_notes = source_notes
    output_system.draft_payload = copy.deepcopy(output_boundary)

    output_version = session.get(OutputSystemVersion, version_id)
    if output_version is None:
        output_version = OutputSystemVersion(
            id=version_id,
            output_system_id=object_id,
            version_number=1,
            schema_version=1,
            payload_schema_name="cinder.output_boundary.locked_final_drive_vehicle",
            payload_schema_version=1,
            validation_status="valid",
            validation_messages=[],
            created_by_user_id=user_id,
            release_notes=release_notes,
            visibility_at_release="public",
            attribution_institution_id=institution_id,
            attribution_label="McMaster Baja Racing" if institution_id is not None else None,
        )
        session.add(output_version)
    output_version.output_boundary_template = copy.deepcopy(output_boundary)
    output_version.summary = _output_summary(output_boundary)
    output_version.payload_hash = canonical_json_hash(output_boundary)
    output_system.released_version_id = version_id


def _upsert_vehicle_assembly_seed(
    session: Session,
    *,
    account_id: str,
    user_id: str | None,
    institution_id: str | None,
    object_id: str,
    version_id: str,
    output_version_id: str,
    default_tune_id: str,
    name: str,
    slug: str,
    description: str,
    catalog_priority: int,
    is_default: bool,
    vehicle_mass_kg: float,
    vehicle_mass_lb: float,
) -> None:
    assembly = session.get(VehicleAssembly, object_id)
    if assembly is None:
        assembly = VehicleAssembly(id=object_id, account_id=account_id)
        session.add(assembly)
    assembly.name = name
    assembly.slug = slug
    assembly.description = description
    assembly.visibility = "public"
    assembly.gallery_listed = True
    assembly.lifecycle_status = "active"
    assembly.catalog_status = "seeded_example"
    assembly.catalog_priority = catalog_priority
    assembly.is_default = is_default
    assembly.source_label = "Seeded Baja baseline"
    assembly.source_notes = f"Example {vehicle_mass_lb:.0f} lb vehicle assembly tying seeded engine, CVT, and output system together."
    assembly.draft_payload = {
        "engine_version_id": SEED_ENGINE_VERSION_ID,
        "cvt_design_version_id": SEED_CVT_VERSION_ID,
        "output_system_version_id": output_version_id,
    }

    assembly_payload = {
        "notes": f"Seeded Baja {vehicle_mass_lb:.0f} lb baseline. Runs freeze the fully resolved CINDER case.",
        "default_tune_id": default_tune_id,
        "default_load_case_id": SEED_LOAD_CASE_ID,
    }
    version = session.get(VehicleAssemblyVersion, version_id)
    if version is None:
        version = VehicleAssemblyVersion(
            id=version_id,
            vehicle_assembly_id=object_id,
            version_number=1,
            schema_version=1,
            payload_schema_name="cvt_simulator.vehicle_assembly",
            payload_schema_version=1,
            validation_status="valid",
            validation_messages=[],
            created_by_user_id=user_id,
            release_notes=f"Initial seeded {vehicle_mass_lb:.0f} lb vehicle assembly.",
            visibility_at_release="public",
            attribution_institution_id=institution_id,
            attribution_label="McMaster Baja Racing" if institution_id is not None else None,
        )
        session.add(version)
    version.engine_version_id = SEED_ENGINE_VERSION_ID
    version.cvt_design_version_id = SEED_CVT_VERSION_ID
    version.output_system_version_id = output_version_id
    version.assembly_payload = assembly_payload
    version.summary = {
        "kind": "baja_baseline",
        "name": name,
        "vehicle_mass_kg": vehicle_mass_kg,
        "vehicle_mass_lb": vehicle_mass_lb,
    }
    version.payload_hash = canonical_json_hash(assembly_payload)
    assembly.released_version_id = version_id


def _upsert_tune_seed(
    session: Session,
    *,
    tune_id: str,
    account_id: str,
    vehicle_assembly_id: str,
    cvt_design_id: str,
    name: str,
    values: JsonDict,
    notes: str,
) -> None:
    tune = session.get(Tune, tune_id)
    if tune is None:
        session.add(
            Tune(
                id=tune_id,
                account_id=account_id,
                vehicle_assembly_id=vehicle_assembly_id,
                cvt_design_id=cvt_design_id,
                name=name,
                values=copy.deepcopy(values),
                notes=notes,
            )
        )
    else:
        tune.name = name
        tune.vehicle_assembly_id = vehicle_assembly_id
        tune.cvt_design_id = cvt_design_id
        merged_values = copy.deepcopy(values)
        merged_values.update(copy.deepcopy(tune.values or {}))
        tune.values = merged_values
        tune.notes = tune.notes or notes


def _upsert_load_case_seed(
    session: Session,
    *,
    load_case_id: str,
    account_id: str,
    name: str,
    kind: str,
    payload: JsonDict,
) -> None:
    load_case = session.get(LoadCase, load_case_id)
    if load_case is None:
        session.add(
            LoadCase(
                id=load_case_id,
                account_id=account_id,
                name=name,
                kind=kind,
                visibility="public",
                payload=copy.deepcopy(payload),
            )
        )
    else:
        load_case.name = name
        load_case.kind = kind
        load_case.visibility = "public"
        load_case.payload = copy.deepcopy(payload)


def _with_vehicle_mass(output_boundary: JsonDict, mass_kg: float) -> JsonDict:
    boundary = copy.deepcopy(output_boundary)
    boundary.setdefault("vehicle", {})["mass_kg"] = mass_kg
    return boundary


def _load_case_payload(
    base_load_case: JsonDict,
    *,
    grade_angle_rad: float | None = None,
    road_profile: JsonDict | None = None,
    metadata: JsonDict | None = None,
) -> JsonDict:
    payload = copy.deepcopy(base_load_case)
    if road_profile is None:
        if grade_angle_rad is None:
            raise ValueError("grade_angle_rad or road_profile must be supplied.")
        road_profile = {
            "kind": "constant_grade",
            "grade_angle_rad": grade_angle_rad,
        }
    payload.setdefault("output_boundary_overrides", {})["road_profile"] = copy.deepcopy(
        road_profile
    )
    if metadata is not None:
        payload.setdefault("metadata", {}).update(copy.deepcopy(metadata))
    return payload


def _flat_then_hill_road_profile() -> JsonDict:
    return {
        "kind": "piecewise_constant_grade",
        "segments": [
            {"start_distance_m": 0.0, "grade_angle_rad": 0.0},
            {
                "start_distance_m": SEED_FLAT_RUNUP_DISTANCE_M,
                "grade_angle_rad": SEED_HILL_30_DEG_RAD,
            },
        ],
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
    """Tunable knobs exposed by the current lightweight frontend.

    The frontend intentionally edits tune values only. These parameters map tune
    keys to JSON-pointer paths inside a released CVT design's CINDER assembly;
    engine, vehicle/output, load-case, and execution data stay owned by their
    own database objects.
    """

    return {
        "parameters": [
            {
                "key": "flyweight_mass_kg",
                "label": "Flyweight mass",
                "description": "Mass of the input centrifugal-ramp actuator.",
                "group": "primary",
                "kind": "number",
                "unit": "kg",
                "dimension": "mass",
                "path": "/pulleys/input/components/0/flyweight_mass_kg",
                "default": 0.8,
                "min": 0.1,
                "max": 1.5,
            },
            {
                "key": "primary_spring_stiffness_N_per_m",
                "label": "Primary spring rate",
                "description": "Stiffness of the input axial spring.",
                "group": "primary",
                "kind": "number",
                "unit": "N/m",
                "dimension": "stiffness",
                "path": "/pulleys/input/components/1/stiffness_N_per_m",
                "default": 35000.0,
                "min": 0.0,
                "max": 200000.0,
            },
            {
                "key": "primary_spring_initial_compression_m",
                "label": "Primary spring pretension",
                "description": "Initial compression of the input axial spring.",
                "group": "primary",
                "kind": "number",
                "unit": "m",
                "dimension": "length",
                "path": "/pulleys/input/components/1/initial_compression_m",
                "default": 0.1046145479692159,
                "min": 0.0,
                "max": 0.2,
            },
            {
                "key": "primary_ramp_profile",
                "label": "Ramp geometry",
                "description": "Input centrifugal-ramp profile.",
                "group": "ramp",
                "kind": "ramp",
                "unit": "1",
                "path": "/pulleys/input/components/0/radial_displacement_profile",
            },
            {
                "key": "secondary_torsional_stiffness_Nm_per_rad",
                "label": "Secondary torsion spring rate",
                "description": "Torsional stiffness of the output torque-reaction component.",
                "group": "secondary",
                "kind": "number",
                "unit": "N·m/rad",
                "path": "/pulleys/output/components/1/torsional_stiffness_Nm_per_rad",
                "default": 25.0,
                "min": 0.0,
                "max": 1000.0,
            },
            {
                "key": "secondary_spring_stiffness_N_per_m",
                "label": "Secondary compression spring rate",
                "description": "Stiffness of the output axial spring.",
                "group": "secondary",
                "kind": "number",
                "unit": "N/m",
                "dimension": "stiffness",
                "path": "/pulleys/output/components/0/stiffness_N_per_m",
                "default": 30000.0,
                "min": 0.0,
                "max": 200000.0,
            },
            {
                "key": "secondary_initial_twist_rad",
                "label": "Secondary rotational spring pretension",
                "description": "Initial twist of the output torque-reaction component.",
                "group": "secondary",
                "kind": "number",
                "unit": "rad",
                "dimension": "angle",
                "path": "/pulleys/output/components/1/initial_twist_rad",
                "default": 5.235987755982989,
                "min": 0.0,
                "max": 7.0,
            },
            {
                "key": "secondary_spring_initial_compression_m",
                "label": "Secondary linear spring pretension",
                "description": "Initial compression of the output axial spring.",
                "group": "secondary",
                "kind": "number",
                "unit": "m",
                "dimension": "length",
                "path": "/pulleys/output/components/0/initial_compression_m",
                "default": 0.11,
                "min": 0.0,
                "max": 0.2,
            },
            {
                "key": "secondary_helix_profile",
                "label": "Helix geometry",
                "description": "Output helical coupling profile.",
                "group": "helix",
                "kind": "ramp",
                "unit": "1",
                "path": "/pulleys/output/helical_coupling/profile/circumferential_profile",
            },
        ]
    }


def _component_by_kind(cinder_assembly: JsonDict, mount: str, kind: str) -> JsonDict | None:
    components = cinder_assembly.get("pulleys", {}).get(mount, {}).get("components", [])
    if not isinstance(components, list):
        return None
    for component in components:
        if isinstance(component, dict) and component.get("kind") == kind:
            return component
    return None


def _extract_baseline_tune(cinder_assembly: JsonDict) -> JsonDict:
    values: JsonDict = {}
    input_ramp = _component_by_kind(cinder_assembly, "input", "centrifugal_ramp")
    input_spring = _component_by_kind(cinder_assembly, "input", "axial_spring")
    output_spring = _component_by_kind(cinder_assembly, "output", "axial_spring")
    output_helix = _component_by_kind(cinder_assembly, "output", "helical_torque_reaction")

    if input_ramp is not None:
        for source_key, tune_key in (
            ("flyweight_mass_kg", "flyweight_mass_kg"),
            ("radial_displacement_profile", "primary_ramp_profile"),
        ):
            if source_key in input_ramp:
                values[tune_key] = copy.deepcopy(input_ramp[source_key])

    if input_spring is not None:
        for source_key, tune_key in (
            ("stiffness_N_per_m", "primary_spring_stiffness_N_per_m"),
            ("initial_compression_m", "primary_spring_initial_compression_m"),
        ):
            if source_key in input_spring:
                values[tune_key] = copy.deepcopy(input_spring[source_key])

    if output_spring is not None:
        for source_key, tune_key in (
            ("stiffness_N_per_m", "secondary_spring_stiffness_N_per_m"),
            ("initial_compression_m", "secondary_spring_initial_compression_m"),
        ):
            if source_key in output_spring:
                values[tune_key] = copy.deepcopy(output_spring[source_key])

    if output_helix is not None:
        for source_key, tune_key in (
            ("torsional_stiffness_Nm_per_rad", "secondary_torsional_stiffness_Nm_per_rad"),
            ("initial_twist_rad", "secondary_initial_twist_rad"),
        ):
            if source_key in output_helix:
                values[tune_key] = copy.deepcopy(output_helix[source_key])

    try:
        values["secondary_helix_profile"] = copy.deepcopy(
            cinder_assembly["pulleys"]["output"]["helical_coupling"]["profile"][
                "circumferential_profile"
            ]
        )
    except (KeyError, TypeError):
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
