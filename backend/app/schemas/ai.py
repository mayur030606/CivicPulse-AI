from pydantic import BaseModel, Field, field_validator

from app.models.enums import ComplaintCategory, Priority, Severity


class TranscriptionResponse(BaseModel):
    text: str
    language: str | None = None


class UnderstandingRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    language: str | None = Field(default=None, max_length=16)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Complaint text must not be empty.")
        return value.strip()


class UnderstandingResponse(BaseModel):
    summary: str
    description: str
    category: ComplaintCategory
    severity: Severity
    priority: Priority
    responsible_department: str
    language: str | None = None
    location_hint: str | None = None
    matched_keywords: list[str] = Field(default_factory=list)
    severity_signals: list[str] = Field(default_factory=list)
    explanation: str
    needs_review: bool
    provider: str
    confidence: float | None = Field(default=None, ge=0, le=1)


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    language: str = Field(default="en", max_length=16)


class Detection(BaseModel):
    label: str = Field(
        description=(
            "Detected object label. The default YOLO model uses generic COCO "
            "labels (person, car, truck, ...) and does not classify civic "
            "issues such as potholes or illegal dumping."
        )
    )
    confidence: float = Field(ge=0, le=1)
    box: list[float] | None = None


class ImageAnalysisResponse(BaseModel):
    detections: list[Detection]
