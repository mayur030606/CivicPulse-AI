"""AI endpoints.

These routes are intentionally thin wrappers. Prisma STT and Timbre TTS are
implemented, and complaint understanding uses an explainable deterministic
provider in Phase 1. Evon remains available as a stub for future integration.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.core.config import get_settings
from app.core.rate_limit import (
    AI_ANALYZE_IMAGE_POLICY,
    AI_UNDERSTAND_POLICY,
    RATE_LIMIT_429_RESPONSE,
    VOICE_SPEAK_POLICY,
    VOICE_TRANSCRIBE_POLICY,
    rate_limit,
)
from app.core.uploads import (
    UploadValidationError,
    read_upload_limited,
    validate_image_upload,
)
from app.schemas.ai import (
    Detection,
    ImageAnalysisResponse,
    SpeechRequest,
    TranscriptionResponse,
    UnderstandingRequest,
    UnderstandingResponse,
)
from app.services import gnani_prisma, gnani_timbre
from app.services.classification import (
    ClassificationProviderError,
    ClassificationValidationError,
    get_classification_service,
)
from app.services.errors import ServiceNotConfiguredError
from app.services.gnani.prisma import get_prisma_service
from app.services.gnani.timbre import get_timbre_service
from app.services.yolo_service import get_yolo_service

router = APIRouter()


@router.post(
    "/transcribe",
    response_model=TranscriptionResponse,
    dependencies=[Depends(rate_limit(VOICE_TRANSCRIBE_POLICY))],
    responses={
        **RATE_LIMIT_429_RESPONSE,
        413: {"description": "Audio file exceeds the configured size limit."},
        415: {"description": "Unsupported audio format or content type."},
        422: {
            "description": (
                "Invalid or empty audio, audio longer than 30 seconds, or an "
                "unsupported language code."
            )
        },
        501: {"description": "GNANI_API_KEY is not configured."},
        502: {"description": "Gnani returned an invalid or error response."},
        503: {"description": "Gnani is rate limiting or temporarily unavailable."},
        504: {"description": "Gnani did not respond within the timeout."},
    },
)
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str | None = Form(default=None, max_length=16),
) -> TranscriptionResponse:
    settings = get_settings()
    max_bytes = settings.gnani_stt_max_upload_mb * 1024 * 1024

    try:
        upload = await read_upload_limited(
            file, max_bytes=max_bytes, kind="Audio file"
        )
        gnani_prisma.validate_audio_upload(
            upload.data, upload.filename, upload.content_type
        )
    except (UploadValidationError, gnani_prisma.VoiceValidationError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    try:
        result = await get_prisma_service().transcribe(
            audio=upload.data,
            filename=upload.filename or "audio",
            content_type=upload.content_type,
            language=language,
        )
    except ServiceNotConfiguredError:
        raise
    except gnani_prisma.VoiceValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except gnani_prisma.GnaniPrismaTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except gnani_prisma.GnaniPrismaAuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except gnani_prisma.GnaniPrismaUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except gnani_prisma.GnaniPrismaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return TranscriptionResponse(text=result.text, language=result.language)


@router.post(
    "/understand",
    response_model=UnderstandingResponse,
    dependencies=[Depends(rate_limit(AI_UNDERSTAND_POLICY))],
    responses=RATE_LIMIT_429_RESPONSE,
)
async def understand_complaint(
    payload: UnderstandingRequest,
) -> UnderstandingResponse:
    try:
        result = get_classification_service().classify(
            text=payload.text,
            language=payload.language,
        )
    except ClassificationValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ClassificationProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return UnderstandingResponse(
        summary=result.summary,
        description=result.description,
        category=result.category,
        severity=result.severity,
        priority=result.priority,
        responsible_department=result.responsible_department,
        language=result.language,
        location_hint=result.location_hint,
        matched_keywords=list(result.matched_keywords),
        severity_signals=list(result.severity_signals),
        explanation=result.explanation,
        needs_review=result.needs_review,
        provider=result.provider,
        confidence=result.confidence,
    )


@router.post(
    "/speech",
    dependencies=[Depends(rate_limit(VOICE_SPEAK_POLICY))],
    responses=RATE_LIMIT_429_RESPONSE,
)
async def synthesize_speech(payload: SpeechRequest) -> Response:
    try:
        result = await get_timbre_service().synthesize(
            text=payload.text, language=payload.language
        )
    except ServiceNotConfiguredError:
        # Converted to HTTP 501 by the application-level exception handler.
        raise
    except gnani_timbre.TimbreValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except gnani_timbre.GnaniTimbreTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except gnani_timbre.GnaniTimbreAuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except gnani_timbre.GnaniTimbreUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except gnani_timbre.GnaniTimbreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return Response(
        content=result.audio,
        media_type=result.content_type,
        headers={
            "Content-Disposition": 'inline; filename="speech.wav"',
            "Cache-Control": "no-store",
        },
    )


@router.post(
    "/analyze-image",
    response_model=ImageAnalysisResponse,
    dependencies=[Depends(rate_limit(AI_ANALYZE_IMAGE_POLICY))],
    responses={
        **RATE_LIMIT_429_RESPONSE,
        413: {"description": "Image file exceeds the configured size limit."},
        415: {"description": "Unsupported image content type or format."},
        422: {
            "description": (
                "Empty, malformed or truncated image, or dimensions/pixel count "
                "above the configured limit."
            )
        },
        503: {"description": "YOLO/Ultralytics or the configured model is unavailable."},
    },
)
async def analyze_image(file: UploadFile = File(...)) -> ImageAnalysisResponse:
    settings = get_settings()
    max_bytes = settings.yolo_max_upload_mb * 1024 * 1024

    try:
        upload = await read_upload_limited(
            file, max_bytes=max_bytes, kind="Image"
        )
        image = validate_image_upload(upload, settings)
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    try:
        detections = await get_yolo_service().analyze_async(image.data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ImageAnalysisResponse(
        detections=[
            Detection(label=item.label, confidence=item.confidence, box=item.box)
            for item in detections
        ]
    )
