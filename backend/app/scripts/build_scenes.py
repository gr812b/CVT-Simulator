"""Regenerate compact fixed scenes without rerunning or changing demo evidence."""

import gzip
import json

from app.application.cinder_gateway import CinderGateway
from app.application.demo import DEMO_PATH
from app.application.physical_contracts import (
    assembly_with_matching_belt,
    baseline_case,
)
from app.database.hashing import canonical_json_hash
from app.schemas.demo import DemoArtifact


def main():
    gateway = CinderGateway()
    with gzip.open(DEMO_PATH, "rt", encoding="utf-8") as stream:
        demo = DemoArtifact.model_validate_json(stream.read())
    assemblies = {
        "landing": assembly_with_matching_belt(baseline_case()["assembly"]),
        "demo": demo.input_document_snapshot["assembly"],
    }
    for name, assembly in assemblies.items():
        target = DEMO_PATH.parent / f"{name}-scene.json"
        payload = {
            "input_hash": canonical_json_hash(assembly),
            "preview": gateway.assembly_scene(assembly).model_dump(mode="json"),
        }
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
        temporary.replace(target)
        print(f"Saved {target.name}: {target.stat().st_size} bytes")


if __name__ == "__main__":
    main()
