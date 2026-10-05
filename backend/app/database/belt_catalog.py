"""Offline seed snapshot of the supplied belt sheet, with explicit provenance."""

import json
import math
from pathlib import Path

from app.application.physical_contracts import template_document
from app.database import library
from app.database.physical_seed import sample_id
from app.database.seed import SEED_ACCOUNT_ID, SEED_USER_ID
from app.schemas.physical_library import BeltData


def seed_belt_catalog(session):
    source = json.loads(Path(__file__).with_name("catalog_belts.json").read_text())
    density = template_document("belts").data.density_kg_per_m3
    headers = source["values"][4]
    for number, row in enumerate(source["values"][5:], 6):
        if not row:
            continue
        manufacturer, series, part = row[:3]
        if series == "Enduro 100":
            # One canonical belt, seeded with the confirmed 11.5° section.
            continue
        key = f"catalog-belt:{manufacturer}:{series}:{part}"
        binding = library.binding_for("belts")
        if session.get(binding.object_model, sample_id(key)):
            continue
        name = " · ".join((manufacturer, series, part))
        notes = [
            f"Source sheet: {source['sheet']} row {number}, snapshot {source['retrieved_on']}."
        ]
        notes.extend(
            f"{headers[index]}: {row[index]}." for index in range(13, min(len(row), 19))
        )
        if len(row) > 19 and row[19]:
            notes.append(row[19])
        notes.append(
            f"Density {density:g} kg/m³ is the editable CINDER baseline assumption; the source sheet does not specify density."
        )
        if manufacturer == "Measured":
            notes.append(
                "Manufacturer is labelled 'Measured' in the source, not independently identified. Measured bottom width is retained even when the listed half-angle differs."
            )
        elif len(row) < 19:
            notes.append(
                "Angle and pitch-depth status are unspecified in the source. The supplied values are retained; no certification is implied."
            )
        notes.append(
            "Section half-angle is derived from the supplied top width, bottom width and height; the independently listed catalog angle is not used as a fourth constraint."
        )
        data = BeltData(
            outer_length_m=row[3] * 0.0254,
            outer_width_m=row[5] * 0.0254,
            height_m=row[6] * 0.0254,
            half_angle_rad=math.atan((row[5] - row[9]) / (2 * row[6])),
            cord_depth_from_outer_m=row[8] * 0.0254,
            inner_width_m=row[9] * 0.0254,
            density_kg_per_m3=density,
        )
        metadata = {
            "name": name,
            "description": f"{series} belt, part {part}. Dimensions imported from the supplied belt catalog; see source notes for measurements and assumptions.",
            "source_label": "CINDER CVT Design Space Explorer · Belts",
            "source_url": source["source_url"],
            "source_notes": "\n".join(notes),
        }
        obj = library.create_object(
            session,
            resource="belts",
            data={
                "id": sample_id(key),
                "account_id": SEED_ACCOUNT_ID,
                **metadata,
                "visibility": "public",
                "catalog_status": "seeded_example",
                "draft_payload": data.model_dump(),
            },
        )
        library.release_object(
            session,
            resource="belts",
            object_id=obj.id,
            release_data={
                "id": sample_id(f"{key}:r1"),
                "payload": data.model_dump(),
                "visibility_at_release": "public",
                "created_by_user_id": SEED_USER_ID,
                "release_notes": "Imported source snapshot; density is an explicit baseline assumption.",
                "summary": {"physical_metadata": metadata},
            },
        )
