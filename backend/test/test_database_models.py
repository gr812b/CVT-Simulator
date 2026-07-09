"""Database schema and seed coverage for the versioned design model."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base
from app.database.models import (
    Account,
    CVTDesign,
    CVTDesignVersion,
    Engine,
    EngineVersion,
    Institution,
    LoadCase,
    OutputSystemVersion,
    RunArtifact,
    Tune,
    VehicleAssemblyVersion,
)
from app.database.hashing import canonical_json_hash
from app.database.resolver import resolve_simulation_case
from app.database.seed import (
    SEED_ASSEMBLY_VERSION_ID,
    SEED_EXECUTION_PRESET_ID,
    SEED_ENGINE_VERSION_ID,
    SEED_LOAD_CASE_FLAT_THEN_HILL_20_ID,
    SEED_LOAD_CASE_ID,
    SEED_TUNE_ID,
    seed_database,
)
from app.database.session import make_engine, make_session_factory


def build_session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    return engine, factory()


def test_database_schema_contains_design_and_run_tables() -> None:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    tables = set(inspect(engine).get_table_names())
    assert {
        "accounts",
        "users",
        "institutions",
        "account_institution_affiliations",
        "engines",
        "engine_versions",
        "cvt_designs",
        "cvt_design_versions",
        "output_systems",
        "output_system_versions",
        "vehicle_assemblies",
        "vehicle_assembly_versions",
        "tunes",
        "load_cases",
        "execution_presets",
        "runs",
        "run_cache_entries",
        "run_artifacts",
        "favorite_runs",
    }.issubset(tables)


def test_seed_data_splits_cinder_contract_ownership_correctly() -> None:
    _, session = build_session()
    try:
        seed_database(session)
        session.commit()

        assert session.scalar(select(Account).where(Account.name == "Demo Baja Workspace"))
        assert session.scalar(select(Institution).where(Institution.slug == "mcmaster-university"))
        assert session.scalars(select(Institution)).all()

        engine_version = session.scalar(select(EngineVersion))
        assert engine_version is not None
        assert engine_version.input_boundary["equivalent_rotational_inertia_kg_m2"] == 0.1

        cvt_version = session.scalar(select(CVTDesignVersion))
        assert cvt_version is not None
        primary = cvt_version.cinder_assembly["inertias"]["primary"]
        secondary = cvt_version.cinder_assembly["inertias"]["secondary"]
        assert "engine_rotational_inertia_kg_m2" not in primary
        assert "gearbox_input_rotational_inertia_kg_m2" not in secondary
        assert primary["rotating_hardware_inertia_kg_m2"] == 0.005
        assert secondary["fixed_rotating_hardware_inertia_kg_m2"] == 0.1

        output_version = session.scalar(select(OutputSystemVersion))
        assert output_version is not None
        assert (
            output_version.output_boundary_template["direct_secondary_shaft_inertia_kg_m2"] == 0.05
        )
        assert output_version.output_boundary_template["drivetrain_loss_model"] == {"kind": "none"}

        tune = session.get(Tune, SEED_TUNE_ID)
        load_case = session.get(LoadCase, SEED_LOAD_CASE_ID)
        assert tune is not None and tune.values
        assert load_case is not None and load_case.payload["scenario"]["time_span_s"] == [0.0, 30.0]
    finally:
        session.close()


def test_resolver_builds_frozen_simulation_case_from_released_versions() -> None:
    _, session = build_session()
    try:
        seed_database(session)
        session.commit()

        document = resolve_simulation_case(
            session,
            vehicle_assembly_version_id=SEED_ASSEMBLY_VERSION_ID,
            tune_id=SEED_TUNE_ID,
            load_case_id=SEED_LOAD_CASE_ID,
            execution_preset_id=SEED_EXECUTION_PRESET_ID,
        )

        assert document["document_type"] == "cinder_simulation_case"
        assert document["assembly"]["document_type"] == "cinder_cvt_assembly"
        assert document["input_boundary"]["equivalent_rotational_inertia_kg_m2"] == 0.1
        assert document["output_boundary"]["direct_secondary_shaft_inertia_kg_m2"] == 0.05
        assert document["output_boundary"]["drivetrain_loss_model"] == {"kind": "none"}
        assert document["scenario"]["initial_state"]["shift_position_m"] == 0.0
        assert "contract_hash" in document
        assert document["database_resolution"]["tune_snapshot"]

        assembly_version = session.get(VehicleAssemblyVersion, SEED_ASSEMBLY_VERSION_ID)
        assert assembly_version is not None
        assert (
            document["database_resolution"]["engine_version_id"]
            == assembly_version.engine_version_id
        )
    finally:
        session.close()



def test_seeded_flat_then_hill_load_case_resolves_as_piecewise_route() -> None:
    _, session = build_session()
    try:
        seed_database(session)
        session.commit()

        document = resolve_simulation_case(
            session,
            vehicle_assembly_version_id=SEED_ASSEMBLY_VERSION_ID,
            tune_id=SEED_TUNE_ID,
            load_case_id=SEED_LOAD_CASE_FLAT_THEN_HILL_20_ID,
            execution_preset_id=SEED_EXECUTION_PRESET_ID,
        )

        road_profile = document["output_boundary"]["road_profile"]
        assert road_profile == {
            "kind": "piecewise_constant_grade",
            "segments": [
                {"start_distance_m": 0.0, "grade_angle_rad": 0.0},
                {
                    "start_distance_m": 90.0,
                    "grade_angle_rad": 0.5235987755982988,
                },
            ],
        }
    finally:
        session.close()

def test_model_payload_columns_use_jsonb_on_postgres() -> None:
    dialect = postgresql.dialect()
    assert isinstance(EngineVersion.__table__.c.input_boundary.type.dialect_impl(dialect), JSONB)
    assert isinstance(
        CVTDesignVersion.__table__.c.cinder_assembly.type.dialect_impl(dialect), JSONB
    )
    assert isinstance(
        OutputSystemVersion.__table__.c.output_boundary_template.type.dialect_impl(dialect), JSONB
    )
    assert isinstance(LoadCase.__table__.c.payload.type.dialect_impl(dialect), JSONB)
    assert isinstance(RunArtifact.__table__.c.inline_payload.type.dialect_impl(dialect), JSONB)


def test_seed_data_marks_default_catalog_entries_and_schema_metadata() -> None:
    _, session = build_session()
    try:
        seed_database(session)
        session.commit()

        engine = session.scalar(select(Engine).where(Engine.slug == "demo-briggs-10hp"))
        cvt_design = session.scalar(
            select(CVTDesign).where(CVTDesign.slug == "demo-baja-rubber-v-belt-cvt")
        )
        assert engine is not None
        assert cvt_design is not None
        assert engine.lifecycle_status == "active"
        assert engine.catalog_status == "official"
        assert engine.catalog_priority == 100
        assert engine.is_default is True
        assert cvt_design.catalog_status == "seeded_example"
        assert cvt_design.is_default is True

        engine_version = session.get(EngineVersion, engine.released_version_id)
        cvt_version = session.get(CVTDesignVersion, cvt_design.released_version_id)
        assert engine_version is not None
        assert cvt_version is not None
        assert (
            engine_version.payload_schema_name == "cinder.input_boundary.full_throttle_torque_curve"
        )
        assert engine_version.payload_schema_version == 1
        assert engine_version.validation_status == "valid"
        assert engine_version.validation_messages == []
        assert cvt_version.payload_schema_name == "cinder.cvt_assembly"
    finally:
        session.close()


def test_deprecated_versions_resolve_with_warnings_and_unsupported_versions_block() -> None:
    _, session = build_session()
    try:
        seed_database(session)
        session.commit()

        engine_version = session.get(EngineVersion, SEED_ENGINE_VERSION_ID)
        assert engine_version is not None
        replacement = EngineVersion(
            id="00000000-0000-4000-8000-000000000012",
            engine_id=engine_version.engine_id,
            version_number=2,
            input_boundary=dict(engine_version.input_boundary),
            summary=dict(engine_version.summary),
            payload_hash=canonical_json_hash(engine_version.input_boundary),
            schema_version=1,
            payload_schema_name=engine_version.payload_schema_name,
            payload_schema_version=engine_version.payload_schema_version,
            validation_status="valid",
            validation_messages=[],
            visibility_at_release="public",
        )
        session.add(replacement)
        session.flush()
        engine_version.validation_status = "deprecated"
        engine_version.validation_messages = [
            {"code": "full_throttle_only", "message": "Use a throttle map when available."}
        ]
        engine_version.superseded_by_version_id = replacement.id
        engine_version.deprecated_at = datetime.now(UTC)
        session.commit()

        document = resolve_simulation_case(
            session,
            vehicle_assembly_version_id=SEED_ASSEMBLY_VERSION_ID,
            tune_id=SEED_TUNE_ID,
            load_case_id=SEED_LOAD_CASE_ID,
            execution_preset_id=SEED_EXECUTION_PRESET_ID,
        )
        warnings = document["database_resolution"]["version_warnings"]
        assert warnings == [
            {
                "object_type": "engine",
                "version_id": SEED_ENGINE_VERSION_ID,
                "validation_status": "deprecated",
                "superseded_by_version_id": replacement.id,
                "messages": [
                    {
                        "code": "full_throttle_only",
                        "message": "Use a throttle map when available.",
                    }
                ],
            }
        ]

        cvt_version = session.scalar(select(CVTDesignVersion))
        assert cvt_version is not None
        cvt_version.validation_status = "unsupported"
        session.commit()
        with pytest.raises(ValueError, match="unsupported"):
            resolve_simulation_case(
                session,
                vehicle_assembly_version_id=SEED_ASSEMBLY_VERSION_ID,
            )
    finally:
        session.close()
