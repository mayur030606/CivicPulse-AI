from pydantic import BaseModel, ConfigDict, Field, field_validator


class VoiceStatus(BaseModel):
    provider: str
    credentials_configured: bool
    integration_implemented: bool
    message: str


class VoiceSpeakRequest(BaseModel):
    """Request body for Gnani Timbre text-to-speech."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "text": "Your complaint has been registered successfully.",
                    "language": "en-IN",
                },
                {
                    "text": "आपकी शिकायत सफलतापूर्वक दर्ज हो गई है।",
                    "language": "hi-IN",
                },
                {
                    "text": "आपली तक्रार यशस्वीरित्या नोंदवली गेली आहे.",
                    "language": "mr-IN",
                },
            ]
        }
    )

    text: str = Field(
        min_length=1,
        max_length=5000,
        description="Text to synthesize. Maximum 5,000 characters.",
    )
    language: str = Field(
        default="en-IN",
        max_length=32,
        description=(
            "Language of the text. Supported: 'en-IN' (or 'en'/'English'), "
            "'hi-IN' (or 'hi'/'Hindi') and 'mr-IN' (or 'mr'/'Marathi')."
        ),
    )
    voice: str | None = Field(
        default=None,
        max_length=32,
        description=(
            "Optional voice ID from the selected model's catalog. When omitted, "
            "a documented default voice for the language is used. Timbre v2.5 "
            "voices are language-specific; Timbre v3.0 voices support all three "
            "languages."
        ),
    )

    @field_validator("text")
    @classmethod
    def _reject_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be empty")
        return value



class VoiceTranscriptionResponse(BaseModel):
    """Prisma v3.0 response fields exposed by the CivicPulse API."""

    success: bool = Field(default=True, description="True for a successful request.")
    transcript: str = Field(
        description=(
            "Transcribed text. An empty string is a valid result when no speech "
            "was detected."
        )
    )
    detected_language_code: str | None = Field(
        default=None,
        description=(
            "Language detected by Prisma v3.0, for example 'hi-IN'. Absent when "
            "the transcript is empty or the transliterate format is used."
        ),
    )
    model: str | None = Field(
        default=None, description="Model reported by Gnani, e.g. 'prisma-v3.0'."
    )
    request_id: str | None = Field(
        default=None, description="Gnani request correlation id."
    )
    processing_time: float | None = Field(
        default=None, description="Seconds spent transcribing after upload parsing."
    )
    end_to_end_latency: float | None = Field(
        default=None, description="Seconds from request arrival, including upload."
    )
    truncated: bool = Field(
        default=False,
        description=(
            "True when Prisma hit its token limit and the transcript is incomplete."
        ),
    )
