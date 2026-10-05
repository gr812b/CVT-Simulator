"""Read the shipped demo without a database session or simulation execution."""

import gzip
import json
from functools import lru_cache
from pathlib import Path

from app.application.course import course_profile
from app.application.physical_contracts import (
    assembly_with_matching_belt,
    baseline_case,
)
from app.core.errors import ApiProblem
from app.database.hashing import canonical_json_hash
from app.schemas.demo import DemoArtifact, DemoPlaybackResponse
from app.schemas.scene import ScenePreview

DEMO_PATH = Path(__file__).resolve().parents[1] / "demo" / "baja-launch.json.gz"


def saved_scene(name, assembly):
    """Load an offline projection; fixed examples do no actuator work on request."""
    try:
        payload = json.loads((DEMO_PATH.parent / f"{name}-scene.json").read_text())
        if payload["input_hash"] != canonical_json_hash(assembly):
            raise ValueError("Scene input changed")
        return ScenePreview.model_validate(payload["preview"])
    except (OSError, ValueError, KeyError) as exc:
        raise ApiProblem(
            503,
            "scene_unavailable",
            "Rebuild the bundled scene previews with python -m app.scripts.build_scenes.",
        ) from exc


@lru_cache(maxsize=1)
def playback():
    try:
        with gzip.open(DEMO_PATH, "rt", encoding="utf-8") as stream:
            demo = DemoArtifact.model_validate_json(stream.read())
        if (
            canonical_json_hash(demo.input_document_snapshot) != demo.input_hash
            or canonical_json_hash(demo.result) != demo.result_hash
            or demo.result.get("metrics", {}).get("completed") is not True
        ):
            raise ValueError("Invalid retained demo evidence")
        return DemoPlaybackResponse(
            **demo.model_dump(),
            course=course_profile(demo.input_document_snapshot, demo.result),
            scene_geometry=saved_scene(
                "demo", demo.input_document_snapshot["assembly"]
            ).geometry,
        )
    except (OSError, ValueError, EOFError) as exc:
        raise ApiProblem(
            503,
            "demo_unavailable",
            "The recorded demo is unavailable on this installation. "
            "Restore the bundled demo artifact and restart the API.",
        ) from exc


@lru_cache(maxsize=1)
def scene():
    """Fixed, anonymous landing example independent of the retained run."""
    return saved_scene(
        "landing", assembly_with_matching_belt(baseline_case()["assembly"])
    )


@lru_cache(maxsize=1)
def forces():
    from app.application.cinder_gateway import CinderGateway

    demo = playback()
    return CinderGateway().force_playback(
        demo.input_document_snapshot["assembly"], demo.result, demo.scene_geometry
    )
