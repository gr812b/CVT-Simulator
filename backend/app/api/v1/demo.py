"""Anonymous read-only playback; visitors never submit computation."""

from fastapi import APIRouter

from app.application import demo
from app.schemas.demo import DemoPlaybackResponse

router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("", response_model=DemoPlaybackResponse)
def playback():
    return demo.playback()
