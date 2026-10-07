"""Authenticated, non-persisting previews of a CVT hardware working copy."""

from fastapi import APIRouter, Depends

from app.api.v1.dependencies import get_current_principal
from app.application import cvt_editor as service
from app.core.errors import ApiProblem
from app.schemas.cvt_editor import (
    CvtEditorRequest,
    InitialTuneRequest,
    InitialTuneSurface,
    PulleyEditorPreviewRequest,
)
from app.schemas.physical_library import CvtData
from app.schemas.scene import ScenePreview, TuneScenePreview

router = APIRouter(
    prefix="/physical-library/editor",
    tags=["physical library"],
    dependencies=[Depends(get_current_principal)],
)


def _preview(action):
    try:
        return action()
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise ApiProblem(
            422,
            "editor_preview_unavailable",
            "The current geometry cannot be previewed: " + str(exc),
        ) from exc


@router.post("/pulleys", response_model=ScenePreview)
def pulleys(request: PulleyEditorPreviewRequest):
    return _preview(lambda: service.pulley_preview(request.geometry))


@router.post("/mechanism", response_model=ScenePreview)
def mechanism(request: CvtEditorRequest):
    return _preview(lambda: service.mechanism_preview(request.cvt))


@router.post("/initial-tune/surface", response_model=InitialTuneSurface)
def initial_surface(request: CvtEditorRequest):
    return service.initial_tune_surface(request.cvt)


@router.post("/initial-tune/preview", response_model=TuneScenePreview)
def initial_preview(request: InitialTuneRequest):
    return _preview(lambda: service.initial_tune_preview(request.cvt, request.values))


@router.post("/initial-tune/apply", response_model=CvtData)
def initial_apply(request: InitialTuneRequest):
    # The normal physical Save owns the full construction audit and persistence.
    return service.apply_initial_tune(request.cvt, request.values)
