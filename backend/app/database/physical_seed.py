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
    with_belt,
)
from app.database import library
from app.database.seed import SEED_ACCOUNT_ID, SEED_USER_ID, _baseline_tuning_schema
from app.database.tuning import readable_tuning_schema


def sample_id(key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"cinder-web:physical-samples:v1:{key}"))


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
    revised_belt = {**belt, "density_kg_per_m3": belt["density_kg_per_m3"] * 1.02}
    insert(
        "belts",
        "belt",
        "Project baseline rubber belt",
        [
            (belt, "Original project belt dimensions and density.", {}),
            (
                revised_belt,
                "Illustrative revision: density increased 2%; existing CVTs remain on revision 1.",
                {},
            ),
        ],
        default=True,
    )
    other_belt = {**belt, "density_kg_per_m3": belt["density_kg_per_m3"] * 1.1}
    insert(
        "belts",
        "belt-dense",
        "Illustrative denser rubber belt",
        [
            (
                other_belt,
                "Illustrative 10% density variation; same section and outer length.",
                {},
            ),
        ],
    )
    engine = template.data.engine.data.model_dump()
    insert(
        "engines",
        "engine",
        "Project baseline engine curve",
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
        "Project fixed-pivot CVT",
        [
            (
                cvt.assembly,
                "Project fixed-pivot hardware, pinned to original belt revision 1.",
                {"tuning_schema": tuning, "belt_version_id": sample_id("belt:r1")},
            ),
        ],
        default=True,
    )
    cvt.belt.data.density_kg_per_m3 = other_belt["density_kg_per_m3"]
    cvt = with_belt(cvt)
    cvt.assembly["contact"]["kinetic_friction_coefficient"] = 0.5
    insert(
        "cvt-designs",
        "cvt-alternative",
        "Illustrative lower-traction CVT",
        [
            (
                cvt.assembly,
                "Illustrative kinetic coefficient 0.50 and denser belt; geometry unchanged.",
                {
                    "tuning_schema": readable_tuning_schema(cvt.assembly, tuning),
                    "belt_version_id": sample_id("belt-dense:r1"),
                },
            ),
        ],
    )

    vehicle = template.data.vehicle.model_copy(deep=True)
    original_vehicle = vehicle_boundary(vehicle)
    vehicle.mass_kg = 500 * 0.45359237
    insert(
        "output-systems",
        "vehicle",
        "Project vehicle properties",
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
        "Illustrative 400 lb vehicle properties",
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
        "Baja baseline · 500 lb",
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
        "Baja alternative · 400 lb",
        [
            (
                {},
                "Illustrative lighter setup with the lower-traction CVT and denser belt.",
                {
                    **refs,
                    "cvt_design_version_id": sample_id("cvt-alternative:r1"),
                    "output_system_version_id": sample_id("vehicle-light:r1"),
                },
            ),
        ],
    )
