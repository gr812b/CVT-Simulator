"""Public, retained playback evidence; this is not an owned or queued run."""

from datetime import datetime
from typing import Literal

from app.schemas.common import ApiModel, JsonObject
from app.schemas.course import CourseProfile

from .scene import SceneGeometry


class DemoArtifact(ApiModel):
    id: Literal["baja-launch"] = "baja-launch"
    name: str
    description: str
    generated_at: datetime
    runtime_identity: JsonObject
    input_hash: str
    result_hash: str
    input_document_snapshot: JsonObject
    result: JsonObject


class DemoPlaybackResponse(DemoArtifact):
    scene_geometry: SceneGeometry
    course: CourseProfile | None
