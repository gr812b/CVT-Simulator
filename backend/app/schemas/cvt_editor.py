"""Working-copy CVT editor contracts. These requests never persist revisions."""

from pydantic import Field

from .common import ApiModel, JsonObject
from .experiments import TuneField, TuneValues
from .physical_library import CvtData


class PulleyEditorPreviewRequest(ApiModel):
    # Pulley travel needs canonical geometry only. Actuator construction errors
    # must not make this simple hardware preview disappear.
    geometry: JsonObject


class CvtEditorRequest(ApiModel):
    cvt: CvtData


class InitialTuneSurface(ApiModel):
    fields: list[TuneField]
    values: TuneValues


class InitialTuneRequest(CvtEditorRequest):
    values: TuneValues = Field(default_factory=dict)
