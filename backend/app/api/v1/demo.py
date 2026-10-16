"""Anonymous playback and bounded, nonpersistent mechanism studies."""

from threading import BoundedSemaphore

from fastapi import APIRouter, Depends, Request

from app.application import demo
from app.schemas.demo import DemoPlaybackResponse
from app.schemas.scene import ForcePlayback, ScenePreview
from app.application.sliding_block_demo import (
    preview as sliding_block_preview,
    PreviewGeometryError,
)
from app.application.auth_limits import throttle
from app.api.v1.dependencies import require_browser_request
from app.core.errors import ApiProblem
from app.schemas.sliding_block_demo import (
    SlidingBlockDemoResponse,
    SlidingBlockPreviewRequest,
    SlidingBlockPreviewResponse,
    SlidingBlockFinding,
)

router = APIRouter(prefix="/demo", tags=["demo"])
_preview_slots = BoundedSemaphore(2)


@router.get("/sliding-block", response_model=SlidingBlockDemoResponse)
def sliding_block():
    """One bounded, cached geometry sample; no user-supplied computation."""
    return sliding_block_preview()


@router.post(
    "/sliding-block/preview",
    response_model=SlidingBlockPreviewResponse,
    dependencies=[Depends(require_browser_request)],
)
def sliding_block_edit(body: SlidingBlockPreviewRequest, request: Request):
    """Bounded template study, without persistence or simulation submission."""
    throttle(
        request,
        "sliding_block_preview",
        request.client.host if request.client else "unknown",
        limit=90,
        seconds=60,
        error_code="preview_rate_limited",
        message="Too many preview requests. Wait a moment, then retry.",
    )
    if not _preview_slots.acquire(blocking=False):
        raise ApiProblem(429, "preview_busy", "The geometry preview is busy. Retry in a moment.")
    try:
        try:
            result = sliding_block_preview(body.inputs)
            return SlidingBlockPreviewResponse(
                revision=body.revision, preview=result, findings=result.findings
            )
        except ValueError as error:
            finding = SlidingBlockFinding(
                code="unsupported_geometry",
                field=error.field if isinstance(error, PreviewGeometryError) else None,
                message=str(error),
            )
            return SlidingBlockPreviewResponse(
                revision=body.revision, preview=None, findings=[finding]
            )
    finally:
        _preview_slots.release()


@router.get("", response_model=DemoPlaybackResponse)
def playback():
    return demo.playback()


@router.get("/scene", response_model=ScenePreview)
def default_scene():
    return demo.scene()


@router.get("/forces", response_model=ForcePlayback)
def force_playback():
    return demo.forces()
