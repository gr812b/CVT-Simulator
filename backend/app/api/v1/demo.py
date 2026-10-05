"""Anonymous read-only playback; visitors never submit computation."""

from app.application import demo
from app.schemas.demo import DemoPlaybackResponse
from app.schemas.scene import ScenePreview
from fastapi import APIRouter

router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("", response_model=DemoPlaybackResponse)
def playback():
    return demo.playback()


@router.get("/scene", response_model=ScenePreview)
def default_scene():
    return demo.scene()
