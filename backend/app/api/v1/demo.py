"""Anonymous read-only playback; visitors never submit computation."""

from fastapi import APIRouter

from app.application import demo
from app.schemas.demo import DemoPlaybackResponse
from app.schemas.scene import ForcePlayback, ScenePreview
from app.application.sliding_block_demo import preview as sliding_block_preview
from app.schemas.sliding_block_demo import SlidingBlockDemoResponse

router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/sliding-block", response_model=SlidingBlockDemoResponse)
def sliding_block():
    """One bounded, cached geometry sample; no user-supplied computation."""
    return sliding_block_preview()


@router.get("", response_model=DemoPlaybackResponse)
def playback():
    return demo.playback()


@router.get("/scene", response_model=ScenePreview)
def default_scene():
    return demo.scene()


@router.get("/forces", response_model=ForcePlayback)
def force_playback():
    return demo.forces()
