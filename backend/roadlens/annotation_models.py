"""Manual vehicle identities, separately stored predicted hypotheses and their pixel space."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .calibration_models import ImageGeometry

Category = Literal["car", "truck", "bus", "motorcycle"]
Box = tuple[float, float, float, float]


class AnnotationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class GroundTruthObject(AnnotationModel):
    identity: str = Field(min_length=1, max_length=120)
    category: Category
    bbox: Box | None = None
    occluded: bool = Field(default=False, strict=True)
    partial_visibility: bool = Field(default=False, strict=True)
    entry: bool = Field(default=False, strict=True)
    exit: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def visible_box(self):
        if self.bbox is None and not self.occluded:
            raise ValueError("An object without a visible bounding box must be marked occluded.")
        return self


class TrackPrediction(AnnotationModel):
    predicted_track_id: int = Field(ge=1, strict=True)
    category: Category
    bbox: Box
    confidence: float = Field(ge=0, le=1)


class AnnotatedFrame(AnnotationModel):
    index: int = Field(ge=1, le=100000, strict=True)
    timestamp_s: float | None = None
    reviewed: bool = Field(default=False, strict=True)
    objects: list[GroundTruthObject] = Field(default_factory=list, max_length=200)
    predictions: list[TrackPrediction] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def unique_labels(self):
        identities = [item.identity for item in self.objects]
        predictions = [item.predicted_track_id for item in self.predictions]
        if len(set(identities)) != len(identities):
            raise ValueError("Ground-truth identities must be unique within each frame.")
        if len(set(predictions)) != len(predictions):
            raise ValueError("Predicted IDs must be unique within each frame.")
        return self


class ProposalRequest(AnnotationModel):
    start_index: int = Field(default=1, ge=1, le=100000, strict=True)
    end_index: int = Field(default=25, ge=1, le=100000, strict=True)
    input_size: Literal[320, 416, 640] = 416
    confidence: float = Field(default=.35, ge=.05, le=.95)
    tracker: Literal["baseline", "improved"] = "improved"

    @model_validator(mode="after")
    def bounded_range(self):
        if self.end_index < self.start_index or self.end_index-self.start_index >= 100:
            raise ValueError("A proposal run must cover one to one hundred consecutive frames.")
        return self


class ProposalMetadata(ProposalRequest):
    elapsed_ms: float = Field(ge=0)
    model: str = Field(default="YOLOX-S INT8", max_length=200)
    identity_scope: Literal["single_run"] = "single_run"


class AnnotationDocument(AnnotationModel):
    schema_version: Literal[1] = 1
    field_session_id: str = Field(min_length=1, max_length=160)
    source_id: str = Field(min_length=1, max_length=240)
    geometry: ImageGeometry
    revision: int = Field(default=0, ge=0, strict=True)
    provenance: Literal["synthetic", "recorded_unverified", "independent_reference"] = "recorded_unverified"
    frames: list[AnnotatedFrame] = Field(default_factory=list, max_length=10000)
    proposal_metadata: ProposalMetadata | None = None

    @model_validator(mode="after")
    def consistent_frames(self):
        indices = [frame.index for frame in self.frames]
        if len(set(indices)) != len(indices):
            raise ValueError("Frame indices must be unique.")
        if sum(len(frame.objects)+len(frame.predictions) for frame in self.frames) > 100000:
            raise ValueError("Annotation documents are limited to 100000 object observations.")
        categories = {}
        for frame in self.frames:
            for item in frame.objects:
                if item.identity in categories and categories[item.identity] != item.category:
                    raise ValueError("One ground-truth identity must keep the same vehicle category.")
                categories[item.identity] = item.category
            for item in [*frame.objects, *frame.predictions]:
                if item.bbox is not None:
                    x1, y1, x2, y2 = item.bbox
                    if not (0 <= x1 < x2 <= self.geometry.width and 0 <= y1 < y2 <= self.geometry.height):
                        raise ValueError("Boxes must have positive area and stay within the document's image geometry.")
        self.frames.sort(key=lambda frame: frame.index)
        return self
