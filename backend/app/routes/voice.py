"""Voice endpoints.

``POST /api/v1/voice/transcribe`` proxies short audio clips to Gnani Prisma
v3.0 and returns the provider's transcript and detected language.
``POST /api/v1/voice/speak`` synthesizes speech with Gnani Timbre and returns a
WAV audio file. Neither endpoint fabricates a response: transport,
authentication and provider errors are reported as HTTP errors instead.
"""

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.core.config import get_settings
from app.core.rate_limit import (
    RATE_LIMIT_429_RESPONSE,
    VOICE_SPEAK_POLICY,
    VOICE_TRANSCRIBE_POLICY,
    rate_limit,
)
from app.core.uploads import UploadValidationError, read_upload_limited
from app.schemas.voice import (
    VoiceSpeakRequest,
    VoiceStatus,
    VoiceTranscriptionResponse,
)
from app.services import gnani_prisma, gnani_timbre
from app.services.errors import ServiceNotConfiguredError
from app.services.gnani_prisma import get_gnani_prisma_service
from app.services.gnani_timbre import get_gnani_timbre_service

logger = logging.getLogger(__name__)

router = APIRouter()

_AUDIO_FILE_DESCRIPTION = (
    "Audio clip to transcribe. Supported formats: WAV, MP3, OGG, FLAC, AAC, "
    "M4A. Maximum size: 10 MB (configurable). Maximum duration: 30 seconds."
)


@router.get("/status", response_model=VoiceStatus)
def voice_status() -> VoiceStatus:
    settings = get_settings()
    credentials_configured = bool(
        settings.gnani_api_key.strip()
        and (
            settings.gnani_stt_url
            or settings.gnani_tts_base_url
            or settings.gnani_base_url
        )
    )

    return VoiceStatus(
        provider="gnani",
        credentials_configured=credentials_configured,
        integration_implemented=True,
        message=(
            "Gnani Prisma v3.0 speech-to-text is available at "
            "POST /api/v1/voice/transcribe and Gnani Timbre text-to-speech is "
            "available at POST /api/v1/voice/speak. Evon NLU remains "
            "unimplemented."
        ),
    )


@router.post(
    "/transcribe",
    response_model=VoiceTranscriptionResponse,
    summary="Transcribe a short audio clip with Gnani Prisma",
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
        502: {
            "description": (
                "Gnani rejected the credentials or returned an invalid/error "
                "response."
            )
        },
        503: {"description": "Gnani is rate limiting or temporarily unavailable."},
        504: {"description": "Gnani did not respond within the timeout."},
    },
)
async def transcribe_audio(
    audio_file: UploadFile = File(..., description=_AUDIO_FILE_DESCRIPTION),
    language_code: str = Form(
        default="indic-auto",
        description=(
            "Prisma v3.0 language code. Use 'indic-auto' for automatic "
            "detection, or a comma-separated list of 1-4 codes such as "
            "'hi-IN,en-IN'."
        ),
    ),
) -> VoiceTranscriptionResponse:
    settings = get_settings()
    max_bytes = settings.gnani_stt_max_upload_mb * 1024 * 1024

    try:
        upload = await read_upload_limited(
            audio_file, max_bytes=max_bytes, kind="Audio file"
        )
        gnani_prisma.validate_audio_upload(
            upload.data, upload.filename, upload.content_type
        )
    except (UploadValidationError, gnani_prisma.VoiceValidationError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    try:
        result = await get_gnani_prisma_service().transcribe(
            audio=upload.data,
            filename=upload.filename or "audio",
            content_type=upload.content_type,
            language_code=language_code,
        )
    except ServiceNotConfiguredError:
        # Converted to HTTP 501 by the application-level exception handler.
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

    return VoiceTranscriptionResponse(
        success=True,
        transcript=result.transcript,
        detected_language_code=result.detected_language_code,
        model=result.model,
        request_id=result.request_id,
        processing_time=result.processing_time,
        end_to_end_latency=result.end_to_end_latency,
        truncated=result.truncated,
    )


@router.post(
    "/speak",
    response_class=Response,
    summary="Synthesize speech with Gnani Timbre",
    dependencies=[Depends(rate_limit(VOICE_SPEAK_POLICY))],
    responses={
        **RATE_LIMIT_429_RESPONSE,
        200: {
            "description": "Synthesized speech as a WAV audio file.",
            "content": {
                "audio/wav": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        },
        422: {
            "description": (
                "Empty/blank text, text over 5,000 characters, an unsupported "
                "language, an invalid voice, or text rejected by the provider."
            )
        },
        501: {"description": "GNANI_API_KEY is not configured."},
        502: {
            "description": (
                "Gnani rejected the credentials/scope or returned an invalid "
                "response."
            )
        },
        503: {"description": "Gnani is rate limiting or temporarily unavailable."},
        504: {"description": "Gnani did not respond within the timeout."},
    },
)
async def synthesize_speech(payload: VoiceSpeakRequest) -> Response:
    try:
        result = await get_gnani_timbre_service().synthesize(
            text=payload.text,
            language=payload.language,
            voice=payload.voice,
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

