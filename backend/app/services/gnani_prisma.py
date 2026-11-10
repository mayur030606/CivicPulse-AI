"""Gnani Prisma v3.0 speech-to-text (official REST contract).

Official documentation:
https://docs.gnani.ai/api/STT/speech-to-text

The provider is called with ``multipart/form-data`` using the ``audio_file``
field, the ``X-API-Key-ID`` header, model ``prisma-v3.0`` and language
``indic-auto`` by default. The API key is read from ``GNANI_API_KEY`` and is
never included in responses, logs or exceptions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

import httpx
from mutagen import File as MutagenFile
from mutagen.aac import AAC
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.wave import WAVE

from app.core.config import Settings, get_settings
from app.services.errors import ServiceNotConfiguredError

logger = logging.getLogger(__name__)

# Provider limits from the official documentation.
MAX_DURATION_SECONDS = 30.0
SUPPORTED_AUDIO_EXTENSIONS = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".m4a": "audio/mp4",
}

ALLOWED_CONTENT_TYPES = {
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/ogg",
    "application/ogg",
    "audio/flac",
    "audio/x-flac",
    "audio/aac",
    "audio/x-aac",
    "audio/aacp",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
    "application/octet-stream",
    "",
}

SUPPORTED_LANGUAGE_CODES = {
    "bn-IN",
    "en-IN",
    "gu-IN",
    "hi-IN",
    "kn-IN",
    "ml-IN",
    "mr-IN",
    "pa-IN",
    "ta-IN",
    "te-IN",
}

# Provider error types that mean the uploaded audio/language was invalid.
_AUDIO_ERROR_MESSAGES = {
    "EMPTY_AUDIO": "Uploaded audio file is empty.",
    "UNSUPPORTED_AUDIO_FORMAT": (
        "Unsupported audio format. Use WAV, MP3, OGG, FLAC, AAC or M4A."
    ),
    "AUDIO_CONVERSION_ERROR": (
        "The audio file could not be decoded. Upload a valid WAV, MP3, OGG, "
        "FLAC, AAC or M4A file."
    ),
    "MAX_AUDIO_DURATION_EXCEEDED": (
        "Audio duration exceeds the maximum allowed 30 seconds."
    ),
    "INVALID_LANGUAGE_CODE": "Unsupported language code.",
    "MODEL_UNSUPPORTED_LANGUAGE": (
        "The selected language is not supported by prisma-v3.0."
    ),
}


class VoiceValidationError(ValueError):
    """Invalid audio/language input that should be reported to the client."""

    status_code = 422


class UnsupportedAudioFormatError(VoiceValidationError):
    status_code = 415


class AudioTooLargeError(VoiceValidationError):
    status_code = 413


class GnaniPrismaError(RuntimeError):
    """Base error for an unsuccessful provider call."""

    status_code = 502


class GnaniPrismaAuthError(GnaniPrismaError):
    """The provider rejected the configured credentials or scopes."""

    status_code = 502


class GnaniPrismaUnavailableError(GnaniPrismaError):
    """The provider is rate limiting, unavailable, or returned a 5xx."""

    status_code = 503


class GnaniPrismaTimeoutError(GnaniPrismaError):
    """The provider did not respond within the configured timeout."""

    status_code = 504


@dataclass(slots=True)
class TranscriptionResult:
    transcript: str
    detected_language_code: str | None = None
    model: str | None = None
    request_id: str | None = None
    processing_time: float | None = None
    end_to_end_latency: float | None = None
    truncated: bool = False
    raw: dict[str, Any] | None = None

    # Backwards-compatible aliases for the pre-existing /ai/transcribe schema.
    @property
    def text(self) -> str:
        return self.transcript

    @property
    def language(self) -> str | None:
        return self.detected_language_code


def validate_audio_file(filename: str | None, content_type: str | None) -> str:
    """Validate the file extension and declared MIME type.

    Returns the normalised extension (for example ``.wav``). The provider
    selects the decoder from the file-name extension, so the extension is the
    authoritative check. A declared content type is also rejected when it is
    clearly not an audio type accepted by Gnani.
    """

    extension = Path(filename or "").suffix.lower()
    if extension not in SUPPORTED_AUDIO_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_AUDIO_EXTENSIONS))
        raise UnsupportedAudioFormatError(
            f"Unsupported audio format '{extension or 'unknown'}'. "
            f"Supported formats: {supported}."
        )

    normalised_content_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalised_content_type not in ALLOWED_CONTENT_TYPES:
        raise UnsupportedAudioFormatError(
            f"Unsupported content type '{normalised_content_type}'. "
            "Upload a WAV, MP3, OGG, FLAC, AAC or M4A audio file."
        )

    return extension


def _probe_with(parser: Callable[[BytesIO], Any], audio: bytes) -> float:
    try:
        parsed = parser(BytesIO(audio))
        length = getattr(getattr(parsed, "info", None), "length", None)
        duration = float(length) if length is not None else 0.0
    except Exception as exc:  # mutagen raises format-specific exceptions
        raise VoiceValidationError(
            "The audio file could not be read. Upload a valid WAV, MP3, OGG, "
            "FLAC, AAC or M4A file."
        ) from exc

    if duration <= 0:
        raise VoiceValidationError("The audio file contains no playable audio.")
    return duration


def probe_audio_duration(audio: bytes, extension: str) -> float:
    """Return the audio duration in seconds using mutagen metadata."""

    if not audio:
        raise VoiceValidationError("Uploaded audio file is empty.")

    parsers: dict[str, Callable[[BytesIO], Any]] = {
        ".wav": WAVE,
        ".mp3": MP3,
        ".ogg": MutagenFile,
        ".flac": FLAC,
        ".aac": AAC,
        ".m4a": MP4,
    }
    parser = parsers.get(extension)
    if parser is None:
        raise UnsupportedAudioFormatError(
            f"Unsupported audio format '{extension}'."
        )
    return _probe_with(parser, audio)


def validate_audio_duration(audio: bytes, extension: str) -> float:
    """Validate that the decoded audio does not exceed the 30 second limit."""

    duration = probe_audio_duration(audio, extension)
    if duration > MAX_DURATION_SECONDS:
        raise VoiceValidationError(
            "Audio duration exceeds the maximum allowed 30 seconds."
        )
    return duration


def validate_audio_upload(
    audio: bytes,
    filename: str | None,
    content_type: str | None,
) -> str:
    """Validate an audio upload's declared type and actual decoded content.

    Returns the normalised extension. Both transcription routes use this so the
    legacy ``/ai/transcribe`` alias has the same size, format and duration
    guarantees as ``/voice/transcribe``.
    """

    extension = validate_audio_file(filename, content_type)
    validate_audio_duration(audio, extension)
    return extension


def validate_language_code(language_code: str | None) -> str:
    """Validate a Prisma v3.0 language code or comma-separated language list."""

    value = (language_code or "").strip()
    if not value:
        return "indic-auto"

    if value == "indic-auto":
        return value

    codes = [code.strip() for code in value.split(",") if code.strip()]
    if not 1 <= len(codes) <= 4:
        raise VoiceValidationError(
            "language_code must be 'indic-auto' or a comma-separated list of "
            "1-4 supported language codes."
        )

    unsupported = [code for code in codes if code not in SUPPORTED_LANGUAGE_CODES]
    if unsupported:
        supported = ", ".join(sorted(SUPPORTED_LANGUAGE_CODES))
        raise VoiceValidationError(
            f"Unsupported language code(s): {', '.join(unsupported)}. "
            f"Supported codes: indic-auto, {supported}."
        )
    return ",".join(codes)


def _safe_filename(filename: str | None) -> str:
    """Strip directory components without changing the extension."""

    name = Path(filename or "audio").name
    return name or "audio"


def _provider_error(body: Any) -> tuple[str | None, str | None]:
    """Extract an error type/code and message from the documented envelopes."""

    if not isinstance(body, dict):
        return None, None

    error = body.get("error")
    if isinstance(error, dict):
        error_type = error.get("type")
        return (
            str(error_type) if error_type is not None else None,
            str(error.get("message")) if error.get("message") else None,
        )
    if isinstance(error, str):
        code = body.get("code")
        return str(code) if code is not None else None, str(error)

    detail = body.get("detail")
    if isinstance(detail, dict):
        code = detail.get("error_code")
        message = detail.get("message")
        return (
            str(code) if code is not None else None,
            str(message) if message is not None else None,
        )

    return None, None


class GnaniPrismaService:
    """Thin async client for the Gnani Prisma REST endpoint."""

    service_name = "Gnani Prisma (speech-to-text)"

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client

    @property
    def is_configured(self) -> bool:
        return bool(
            self.settings.gnani_api_key.strip() and self.settings.gnani_stt_url
        )

    def _ensure_configured(self) -> None:
        if not self.is_configured:
            raise ServiceNotConfiguredError(
                f"{self.service_name} is not configured. Set GNANI_API_KEY in "
                "backend/.env."
            )

    async def transcribe(
        self,
        *,
        audio: bytes,
        filename: str,
        content_type: str | None = None,
        language_code: str | None = None,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe an audio clip with Prisma v3.0.

        ``language`` is accepted as a backwards-compatible alias for
        ``language_code`` so the existing ``/api/v1/ai/transcribe`` route keeps
        working.
        """

        self._ensure_configured()

        requested_language = validate_language_code(language_code or language)
        safe_name = _safe_filename(filename)
        extension = Path(safe_name).suffix.lower()
        declared_type = (content_type or "").split(";", 1)[0].strip().lower()
        media_type = SUPPORTED_AUDIO_EXTENSIONS.get(
            extension, "application/octet-stream"
        )
        if declared_type in {"", "application/octet-stream"}:
            declared_type = media_type

        headers = {"X-API-Key-ID": self.settings.gnani_api_key.strip()}
        data = {
            "model": self.settings.gnani_stt_model,
            "language_code": requested_language,
        }
        files = {
            "audio_file": (safe_name, audio, declared_type),
        }

        timeout = httpx.Timeout(
            self.settings.gnani_stt_timeout_seconds,
            connect=min(10.0, self.settings.gnani_stt_timeout_seconds),
        )

        try:
            if self._client is not None:
                response = await self._client.post(
                    self.settings.gnani_stt_url,
                    headers=headers,
                    data=data,
                    files=files,
                )
            else:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        self.settings.gnani_stt_url,
                        headers=headers,
                        data=data,
                        files=files,
                    )
        except httpx.TimeoutException as exc:
            logger.warning("Gnani Prisma STT timed out")
            raise GnaniPrismaTimeoutError(
                "Speech-to-text service timed out. Try again."
            ) from exc
        except httpx.RequestError as exc:
            logger.warning("Gnani Prisma STT request failed: %s", type(exc).__name__)
            raise GnaniPrismaUnavailableError(
                "Speech-to-text service is unreachable. Try again."
            ) from exc

        return self._parse_response(response)

    def _parse_response(self, response: httpx.Response) -> TranscriptionResult:
        try:
            body: Any = response.json()
        except ValueError:
            body = None

        if response.status_code == 200:
            if not isinstance(body, dict) or body.get("success") is not True:
                logger.warning(
                    "Gnani Prisma STT returned an unexpected 200 body"
                )
                raise GnaniPrismaError(
                    "Speech-to-text service returned an unexpected response."
                )

            transcript = body.get("transcript")
            if not isinstance(transcript, str):
                logger.warning(
                    "Gnani Prisma STT response is missing a string transcript"
                )
                raise GnaniPrismaError(
                    "Speech-to-text service returned an unexpected response."
                )

            detected_language = body.get("detected_language_code")
            return TranscriptionResult(
                transcript=transcript,
                detected_language_code=(
                    str(detected_language)
                    if detected_language is not None
                    else None
                ),
                model=(
                    str(body.get("model")) if body.get("model") is not None else None
                ),
                request_id=(
                    str(body.get("request_id"))
                    if body.get("request_id") is not None
                    else None
                ),
                processing_time=(
                    float(body["processing_time"])
                    if isinstance(body.get("processing_time"), (int, float))
                    else None
                ),
                end_to_end_latency=(
                    float(body["end_to_end_latency"])
                    if isinstance(body.get("end_to_end_latency"), (int, float))
                    else None
                ),
                truncated=body.get("truncated") is True,
                raw=body,
            )

        self._raise_for_error(response, body)

    def _raise_for_error(self, response: httpx.Response, body: Any) -> None:
        error_type, _message = _provider_error(body)
        logger.warning(
            "Gnani Prisma STT failed: status=%s error_type=%s",
            response.status_code,
            error_type or "unknown",
        )

        status = response.status_code

        if status in (400, 422):
            if error_type in _AUDIO_ERROR_MESSAGES:
                raise VoiceValidationError(_AUDIO_ERROR_MESSAGES[error_type])
            raise GnaniPrismaError(
                "Speech-to-text provider rejected the request."
            )

        if status in (401, 402, 403):
            raise GnaniPrismaAuthError(
                "Speech-to-text provider rejected the configured credentials."
            )

        if status == 429:
            raise GnaniPrismaUnavailableError(
                "Speech-to-text provider is rate limiting requests. Try again "
                "shortly."
            )

        if status == 504:
            raise GnaniPrismaTimeoutError(
                "Speech-to-text provider did not finish in time. Try again."
            )

        if status >= 500:
            raise GnaniPrismaUnavailableError(
                "Speech-to-text provider is temporarily unavailable. Try again."
            )

        raise GnaniPrismaError("Speech-to-text provider returned an error.")


@lru_cache
def get_gnani_prisma_service() -> GnaniPrismaService:
    return GnaniPrismaService()
