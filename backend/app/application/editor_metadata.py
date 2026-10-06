"""Normalize CINDER's published editor hints into the web editor envelope."""

from app.application.cinder_gateway import CinderGateway
from app.schemas.projections import EditorDocument


def editor_document(gateway: CinderGateway) -> EditorDocument:
    fields = []
    for hint in gateway.editor_schema()["fields"]:
        path = hint["path"]
        field = {
            "path_template": path,
            "label": hint["label"],
            "section": hint["section"],
            "description": "",
            "value_kind": "number",
            "required": True,
            "enum_values": [],
            "exposure": "scenario" if path.startswith(("/scenario/", "/host/")) else "design",
        }
        for key in ("minimum", "maximum", "when"):
            if key in hint:
                field[key] = hint[key]
        if "unit" in hint:
            field["canonical_unit"] = hint["unit"]
        fields.append(field)
    return {
        "fields": fields,
        "supported_discriminators": {},
        "component_catalog": gateway.component_catalog(),
    }
