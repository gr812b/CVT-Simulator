"""Additive sample catalog with stable IDs and deliberately pinned history.

No existing object or revision is rewritten. Illustrative variations are
explicitly labeled; the values originate from the project's runnable preset.
"""

import copy
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.orm import Session

from app.application.physical_contracts import (
    template_document,
    vehicle_boundary,
)
from app.database import library
from app.database.seed import SEED_ACCOUNT_ID, SEED_USER_ID, _baseline_tuning_schema
from app.database.tuning import readable_tuning_schema


def sample_id(key: str) -> str:
    from app.database.seed import (
        SEED_CVT_ID,
        SEED_CVT_VERSION_ID,
        SEED_ENGINE_ID,
        SEED_ENGINE_VERSION_ID,
    )

    aliases = {
        "cvt": SEED_CVT_ID,
        "cvt:r1": SEED_CVT_VERSION_ID,
        "engine": SEED_ENGINE_ID,
        "engine:r1": SEED_ENGINE_VERSION_ID,
    }
    return aliases.get(
        key, str(uuid5(NAMESPACE_URL, f"cinder-web:physical-samples:v1:{key}"))
    )


def seed_physical_catalog(session: Session) -> None:
    template = template_document("setups")
    metadata = {
        "source_label": "CINDER project sample",
        "source_notes": "Illustrative engineering inputs for development; not manufacturer-certified measurements.",
    }

    def insert(resource, key, name, revisions, *, default=False):
        binding = library.binding_for(resource)
        object_id = sample_id(key)
        existing = session.get(binding.object_model, object_id)
        if existing is not None:
            return existing
        obj = library.create_object(
            session,
            resource=resource,
            data={
                "id": object_id,
                "account_id": SEED_ACCOUNT_ID,
                "name": name,
                "description": "Project baseline example."
                if default
                else "Illustrative variation for setup and revision workflows.",
                "visibility": "public",
                "gallery_listed": False,
                "catalog_status": "seeded_example",
                "catalog_priority": 120 if default else 110,
                "is_default": default,
                **metadata,
            },
        )
        for number, (payload, note, extra) in enumerate(revisions, 1):
            physical_meta = {
                "name": name,
                "description": obj.description,
                "source_url": "",
                **metadata,
            }
            release = {
                "id": sample_id(f"{key}:r{number}"),
                "payload": payload,
                "visibility_at_release": "public",
                "created_by_user_id": SEED_USER_ID,
                "release_notes": note,
                "summary": {"physical_metadata": physical_meta},
                **extra,
            }
            version = library.release_object(
                session, resource=resource, object_id=obj.id, release_data=release
            )
            if resource == "cvt-designs":
                version.belt_version_id = extra["belt_version_id"]
            obj.draft_payload = copy.deepcopy(payload)
        session.flush()
        return obj

    belt = template.data.cvt.data.belt.data.model_dump()
    insert(
        "belts",
        "belt",
        "Gaged Enduro 100",
        [
            (
                belt,
                "11.5° half-angle confirmed by Kai; top width derived from measured bottom width and height.",
                {},
            )
        ],
        default=True,
    )
    engine = template.data.engine.data.model_dump()
    insert(
        "engines",
        "engine",
        "Kohler CH440 (Baja Restricted)",
        [
            (
                engine,
                "Torque curve and equivalent inertia from the project baseline.",
                {},
            ),
        ],
        default=True,
    )

    cvt = copy.deepcopy(template.data.cvt.data)
    tuning = readable_tuning_schema(cvt.assembly, _baseline_tuning_schema())
    insert(
        "cvt-designs",
        "cvt",
        "McMaster 2025",
        [
            (
                cvt.assembly,
                "Project fixed-pivot hardware, pinned to original belt revision 1.",
                {"tuning_schema": tuning, "belt_version_id": sample_id("belt:r1")},
            ),
        ],
        default=True,
    )
    # The legacy bootstrap and physical catalog reference the same hardware.
    from app.database.models import CVTDesignVersion

    session.get(CVTDesignVersion, sample_id("cvt:r1")).belt_version_id = sample_id(
        "belt:r1"
    )

    vehicle = template.data.vehicle.model_copy(deep=True)
    original_vehicle = vehicle_boundary(vehicle)
    vehicle.mass_kg = 500 * 0.45359237
    insert(
        "output-systems",
        "vehicle",
        "CINDER Default · vehicle properties",
        [
            (original_vehicle, "Original 300 kg project vehicle.", {}),
            (
                vehicle_boundary(vehicle),
                "Illustrative 500 lb vehicle mass used by the application baseline.",
                {},
            ),
        ],
        default=True,
    )
    vehicle.mass_kg = 400 * 0.45359237
    insert(
        "output-systems",
        "vehicle-light",
        "CINDER Default · 400 lb vehicle properties",
        [
            (vehicle_boundary(vehicle), "Illustrative mass sensitivity example.", {}),
        ],
    )
    refs = {
        "engine_version_id": sample_id("engine:r1"),
        "cvt_design_version_id": sample_id("cvt:r1"),
        "assembly_payload": {},
    }
    insert(
        "vehicle-assemblies",
        "setup",
        "CINDER Default · McMaster Baja · 500 lb",
        [
            (
                {},
                "Original 300 kg configuration.",
                {**refs, "output_system_version_id": sample_id("vehicle:r1")},
            ),
            (
                {},
                "Updated to the application’s illustrative 500 lb configuration; component revisions stay pinned.",
                {**refs, "output_system_version_id": sample_id("vehicle:r2")},
            ),
        ],
        default=True,
    )
    insert(
        "vehicle-assemblies",
        "setup-light",
        "CINDER Default · Baja · 400 lb",
        [
            (
                {},
                "Lighter vehicle using the same McMaster 2025 CVT and Enduro belt.",
                {
                    **refs,
                    "cvt_design_version_id": sample_id("cvt:r1"),
                    "output_system_version_id": sample_id("vehicle-light:r1"),
                },
            ),
        ],
    )
