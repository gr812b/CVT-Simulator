"""Public samples; updates append revisions without changing saved run inputs."""

import math

from app.application.roads import default_scenario, demo_scenario, feature_templates
from app.database.base import utc_now
from app.database.experiment_models import Experiment, ExperimentRevision
from app.database.hashing import canonical_json_hash
from app.database.physical_seed import sample_id
from app.database.seed import SEED_ACCOUNT_ID, SEED_USER_ID
from app.schemas.experiments import ScenarioDocument, SpatialRoad


def _seed_scenarios(session):
    templates = feature_templates()
    examples = [
        ("demo-course", [demo_scenario()]),
        (
            "flat",
            [default_scenario().model_copy(update={"name": "CINDER Default · flat road"})],
        ),
        (
            "hill",
            [
                ScenarioDocument(
                    kind="scenarios",
                    name="CINDER Default · climb and descent",
                    notes="20 m flat launch, 90 m at +20°, then 90 m at −20°. Finish at 200 m.",
                    road=SpatialRoad(
                        features=[
                            templates[0],
                            {**templates[1], "length_m": 90},
                            {**templates[2], "length_m": 90},
                        ]
                    ),
                )
            ],
        ),
        (
            "whoops",
            [
                ScenarioDocument(
                    kind="scenarios",
                    name="CINDER Default · whoops",
                    notes=(
                        "Eight 0.8 m-high whoops at 4 m spacing start after 5 m, "
                        "followed by a flat finish at 200 m."
                    ),
                    road=SpatialRoad(
                        features=[
                            {**templates[0], "name": "Launch", "length_m": 5},
                            templates[5],
                            {
                                **templates[0],
                                "id": "finish",
                                "name": "Finish",
                                "length_m": 163,
                            },
                        ]
                    ),
                ),
            ],
        ),
    ]
    for angle in (-30, -15, 15, 30):
        length = 200.0
        examples.append(
            (
                f"grade:{angle}",
                [
                    ScenarioDocument(
                        kind="scenarios",
                        name=f"CINDER Default · {abs(angle)}° {'uphill' if angle > 0 else 'downhill'} road",
                        notes="Constant road angle. Course mode stops at the finish; timed mode can continue beyond it. Distance is measured along the road surface.",
                        road=SpatialRoad(
                            features=[
                                {
                                    "kind": "slope",
                                    "id": f"grade-{angle}",
                                    "name": f"{angle:+}° road",
                                    "length_m": length,
                                    "angle_rad": math.radians(angle),
                                }
                            ],
                            endpoint="continue_grade",
                        ),
                    )
                ],
            )
        )
    for key, documents in examples:
        object_id = sample_id(f"scenario:{key}")
        existing = session.get(Experiment, object_id)
        if existing:
            if (
                existing.kind == "scenarios"
                and existing.is_sample
                and existing.account_id == SEED_ACCOUNT_ID
            ):
                current = session.get(ExperimentRevision, existing.current_revision_id)
                payload = documents[-1].model_dump(mode="json")
                content_hash = canonical_json_hash(payload)
                if current.content_hash != content_hash:
                    revision = ExperimentRevision(
                        experiment_id=existing.id,
                        number=current.number + 1,
                        document=payload,
                        content_hash=content_hash,
                        created_by_user_id=SEED_USER_ID,
                        change_note="Update the built-in load case definition or description.",
                    )
                    session.add(revision)
                    session.flush()
                    existing.current_revision_id = revision.id
                existing.name = documents[-1].name
                existing.archived = False
            continue
        obj = Experiment(
            id=object_id,
            account_id=SEED_ACCOUNT_ID,
            kind="scenarios",
            name=documents[-1].name,
            is_sample=True,
        )
        session.add(obj)
        session.flush()
        for number, document in enumerate(documents, 1):
            payload = document.model_dump(mode="json")
            revision = ExperimentRevision(
                id=sample_id(f"scenario:{key}:r{number}"),
                experiment_id=obj.id,
                number=number,
                document=payload,
                content_hash=canonical_json_hash(payload),
                created_by_user_id=SEED_USER_ID,
                change_note="Illustrative scenario; grade-only road load, not suspension dynamics.",
                created_at=utc_now(),
            )
            session.add(revision)
            session.flush()
            obj.current_revision_id = revision.id
        session.flush()

    # Retire the replaced defaults without deleting their immutable revisions.
    # Existing runs and explicit revision selections can still resolve them.
    for angle in (-10, -5, 5, 10):
        old = session.get(Experiment, sample_id(f"scenario:grade:{angle}"))
        if (
            old is not None
            and old.kind == "scenarios"
            and old.is_sample
            and old.account_id == SEED_ACCOUNT_ID
            and not old.archived
        ):
            old.archived = True
    session.flush()


def seed_experiments(session):
    _seed_scenarios(session)
    _seed_sample_tunes(session)
    from sqlalchemy import select

    from app.application.experiment_tuning import ensure_default_tune
    from app.database.models import CVTDesignVersion

    for cvt in session.scalars(select(CVTDesignVersion)):
        ensure_default_tune(session, cvt)


def _seed_sample_tunes(session):
    from copy import deepcopy

    from app.application.experiment_tuning import parameters
    from app.application.physical_contracts import baseline_case
    from app.database.models import CVTDesignVersion
    from app.database.resolver import _current_assembly_document
    from app.schemas.experiments import TuneDocument

    cvt = session.get(CVTDesignVersion, sample_id("cvt:r1"))
    assembly = _current_assembly_document(cvt.cinder_assembly, baseline_case()["execution"])
    defaults = {field["key"]: field["default"] for field in parameters(assembly, cvt.tuning_schema)}
    # Section 4.5 / appendix table: exact tip-mass and spring changes from R00.
    cases = [
        ("R00", "Reference", {}, "Reference McMaster configuration."),
        (
            "W85",
            "Lighter weights",
            {"primary_tip_mass": 0.2125},
            "85% of the reference 250 g replaceable tip; body unchanged.",
        ),
        (
            "P300",
            "Stiffer primary spring",
            {
                "primary_spring_stiffness_N_per_m": 38352.0,
                "primary_spring_initial_compression_m": (
                    0.09409049026972177 + assembly["geometry"]["deadzone_shift_m"]
                )
                / 3
                - assembly["geometry"]["deadzone_shift_m"],
            },
            "Three times the primary spring rate, with matched force at engagement.",
        ),
        (
            "U55",
            "Light weights",
            {"primary_tip_mass": 0.1375},
            "55% tip mass; an illustrative demanding case, not an optimized tune.",
        ),
        (
            "D02",
            "Light weights + preload",
            {
                "primary_tip_mass": 0.1625,
                "primary_spring_initial_compression_m": 0.09409049026972177 * 1.15,
            },
            "65% tip mass and 115% primary spring compression.",
        ),
    ]
    for code, label, changes, description in cases:
        key = f"tune:paper:{code}"
        if session.get(Experiment, sample_id(key)):
            continue
        obj = Experiment(
            id=sample_id(key),
            account_id=SEED_ACCOUNT_ID,
            kind="tunes",
            name=f"{code} · {label}",
            cvt_object_id=cvt.cvt_design_id,
            is_sample=True,
        )
        session.add(obj)
        session.flush()
        document = TuneDocument(
            kind="tunes",
            name=obj.name,
            cvt_revision_id=cvt.id,
            values={**deepcopy(defaults), **changes},
            notes=f"Section 4.5 tuning example. {description} Uses the application's corrected Enduro section; does not reproduce the frozen paper results.",
        ).model_dump(mode="json")
        revision = ExperimentRevision(
            id=sample_id(f"{key}:r1"),
            experiment_id=obj.id,
            number=1,
            document=document,
            content_hash=canonical_json_hash(document),
            created_by_user_id=SEED_USER_ID,
            change_note="Section 4.5 sample tune.",
        )
        session.add(revision)
        session.flush()
        obj.current_revision_id = revision.id
    session.flush()


def seed_experiment_fixtures(session, *, account_id, user_id, setup_revision_id, label):
    """Opt-in, clearly labeled run states; never forge a completed result."""
    from copy import deepcopy

    from app.application.cinder_gateway import CinderGateway
    from app.application.physical_contracts import baseline_case
    from app.database.experiment_models import RunNotification
    from app.database.models import (
        CVTDesignVersion,
        EngineVersion,
        OutputSystemVersion,
        Run,
        VehicleAssemblyVersion,
    )
    from app.database.resolver import (
        _current_assembly_document,
        _current_primary_boundary,
        _current_secondary_boundary,
    )

    setup = session.get(VehicleAssemblyVersion, setup_revision_id)
    cvt = session.get(CVTDesignVersion, setup.cvt_design_version_id)
    from app.application.experiment_tuning import ensure_default_tune

    ensure_default_tune(session, cvt)
    engine = session.get(EngineVersion, setup.engine_version_id)
    output = session.get(OutputSystemVersion, setup.output_system_version_id)
    case = baseline_case()
    case["assembly"] = _current_assembly_document(cvt.cinder_assembly, case["execution"])
    case["shaft_boundaries"] = {
        "primary": _current_primary_boundary(engine.input_boundary),
        "secondary": _current_secondary_boundary(output.output_boundary_template),
    }
    case["scenario"]["time_span_s"] = [0, 0.1]
    runtime = CinderGateway().runtime_identity()
    options = {
        "include_reported_segments": False,
        "include_raw_trace": False,
        "execution_profile": "default",
    }
    for state in ("queued", "failed", "cancelled"):
        run_id = sample_id(f"fixture:{label}:run:{state}")
        if session.get(Run, run_id):
            continue
        row = Run(
            id=run_id,
            account_id=account_id,
            created_by_user_id=user_id,
            name=f"Development fixture · {state}",
            status=state,
            source="library",
            request_key=run_id,
            request_hash=canonical_json_hash({"fixture": run_id}),
            vehicle_assembly_version_id=setup.id,
            engine_version_id=setup.engine_version_id,
            cvt_design_version_id=setup.cvt_design_version_id,
            output_system_version_id=setup.output_system_version_id,
            input_contract=deepcopy(case),
            contract_hash=canonical_json_hash(
                {"input": case, "runtime": runtime, "options": options}
            ),
            cinder_model_version=runtime["package_version"],
            input_schema_version=runtime["simulation_case_schema_version"],
            result_contract_version=runtime["simulation_result_contract_version"],
            runtime_identity=runtime,
            execution_options=options,
            provenance={"development_fixture": True, "setup_revision_id": setup.id},
            completed_at=utc_now() if state != "queued" else None,
            error=(
                {
                    "code": "development_fixture",
                    "message": "Deliberately failed development fixture; no simulation was executed.",
                }
                if state == "failed"
                else None
            ),
        )
        session.add(row)
        session.flush()
        if state != "queued":
            session.add(RunNotification(account_id=account_id, user_id=user_id, run_id=row.id))
    session.flush()
