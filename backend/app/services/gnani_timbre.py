"""Gnani Timbre text-to-speech (official Python SDK contract).

Official documentation:
https://docs.gnani.ai/api/TTS/tts-inference
https://github.com/Gnani-AI-Mintlify/gnani-vachana

The service uses the official ``gnani-vachana`` SDK. The SDK sends the
``X-API-Key-ID`` header, calls ``POST /api/v1/tts/inference`` and returns raw
audio bytes. The API key is read from ``GNANI_API_KEY`` and is never included in
responses, logs or exception messages.

The default model is ``timbre-v2.5``. Its voices each have a preferred language,
so requests are mapped to a documented voice for English, Hindi or Marathi. If
``GNANI_TTS_MODEL=timbre-v3.0`` is configured, any v3.0 voice supports all three
languages and the default voice is ``Shivani``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
from dataclasses import dataclass
from functools import lru_cache
from typing import NoReturn

from gnani.tts import (
    APIError,
    AudioConfig,
    AuthenticationError,
    GnaniTTSClient,
    GnaniTTSError,
    SUPPORTED_MODELS,
    TIMBRE_V25_VOICES,
    TIMBRE_V30_VOICES,
)
from requests import exceptions as requests_exceptions

from app.core.config import Settings, get_settings
from app.services.errors import ServiceNotConfiguredError

logger = logging.getLogger(__name__)

MAX_TEXT_CHARS = 5000
CONTENT_TYPE = "audio/wav"
DEFAULT_MODEL = "timbre-v2.5"
DEFAULT_BASE_URL = "https://api.vachana.ai"

# WAV is explicitly requested so the response has a predictable content type and
# a playable RIFF/WAVE container. These values are documented provider defaults.
AUDIO_CONFIG = AudioConfig(
    sample_rate=48000,
    encoding="linear_pcm",
    num_channels=1,
    sample_width=2,
    container="wav",
)

# The project only exposes the three languages requested for CivicPulse. The
# provider itself supports more, but each Timbre v2.5 voice is optimised for one
# preferred language, so limiting the public contract avoids mismatched voices.
LANGUAGE_ALIASES = {
    "en": "en-IN",
    "en-in": "en-IN",
    "english": "en-IN",
    "hi": "hi-IN",
    "hi-in": "hi-IN",
    "hindi": "hi-IN",
    "mr": "mr-IN",
    "mr-in": "mr-IN",
    "marathi": "mr-IN",
}
SUPPORTED_LANGUAGES = ("en-IN", "hi-IN", "mr-IN")

# Source: https://docs.gnani.ai/api/TTS/available-voices
V25_VOICES_BY_LANGUAGE = {
    "en-IN": ("Kaveri", "Trupti", "Devika", "Pranav", "Shlok", "Girish"),
    "hi-IN": (
        "Nalini",
        "Bhavna",
        "Yashvi",
        "Urmila",
        "Jwala",
        "Chitra",
        "Ambuja",
        "Deepak",
        "Roopesh",
        "Vikrant",
        "Hemraj",
        "Jalaj",
        "Omkar",
    ),
    "mr-IN": ("Zahira", "Ishaan"),
}

# All Timbre v3.0 voices speak every supported language. Shivani is a documented
# female voice suitable for customer-support/announcement text.
V30_DEFAULT_VOICE = "Shivani"

# Fail fast at import time if the documented catalog and SDK drift apart.
if not set(V25_VOICES_BY_LANGUAGE["en-IN"]).issubset(TIMBRE_V25_VOICES):
    raise RuntimeError("Timbre v2.5 English voice catalog does not match the SDK.")
if not set(V25_VOICES_BY_LANGUAGE["hi-IN"]).issubset(TIMBRE_V25_VOICES):
    raise RuntimeError("Timbre v2.5 Hindi voice catalog does not match the SDK.")
if not set(V25_VOICES_BY_LANGUAGE["mr-IN"]).issubset(TIMBRE_V25_VOICES):
    raise RuntimeError("Timbre v2.5 Marathi voice catalog does not match the SDK.")
if V30_DEFAULT_VOICE not in TIMBRE_V30_VOICES:
    raise RuntimeError("Timbre v3.0 default voice does not match the SDK.")


class TimbreValidationError(ValueError):
    """Invalid text, language or voice that should be reported to the client."""

    status_code = 422


class GnaniTimbreError(RuntimeError):
    """Base error for an unsuccessful provider call."""

    status_code = 502


class GnaniTimbreAuthError(GnaniTimbreError):
    """The provider rejected the configured credentials or scopes."""

    status_code = 502


class GnaniTimbreUnavailableError(GnaniTimbreError):
    """The provider is rate limiting, unavailable, or returned a 5xx."""

    status_code = 503


class GnaniTimbreTimeoutError(GnaniTimbreError):
    """The provider did not respond within the configured timeout."""

    status_code = 504


@dataclass(slots=True)
class SpeechResult:
    audio: bytes
    content_type: str = CONTENT_TYPE
    model: str = DEFAULT_MODEL
    language: str = "en-IN"
    voice: str = ""


def validate_text(text: str | None) -> str:
    """Strip and validate text before sending it to the provider."""

    value = (text or "").strip()
    if not value:
        raise TimbreValidationError("Text must not be empty.")
    if len(value) > MAX_TEXT_CHARS:
        raise TimbreValidationError(
            f"Text is too long. The maximum length is {MAX_TEXT_CHARS} characters."
        )
    return value


def normalize_language(language: str | None) -> str:
    """Map common English/Hindi/Marathi aliases to BCP-47 codes."""

    value = (language or "").strip()
    normalized = LANGUAGE_ALIASES.get(value.casefold())
    if normalized is None:
        raise TimbreValidationError(
            f"Unsupported language '{value or language}'. Supported languages: "
            "English (en-IN), Hindi (hi-IN), Marathi (mr-IN)."
        )
    return normalized


def _resolve_model(settings: Settings) -> str:
    model = (settings.gnani_tts_model or DEFAULT_MODEL).strip().lower()
    if model not in SUPPORTED_MODELS:
        supported = ", ".join(sorted(SUPPORTED_MODELS))
        raise ServiceNotConfiguredError(
            f"GNANI_TTS_MODEL must be one of: {supported}."
        )
    return model


def _canonical_voice(voice: str, allowed: tuple[str, ...] | frozenset[str]) -> str:
    if voice in allowed:
        return voice

    casefolded = {candidate.casefold(): candidate for candidate in allowed}
    match = casefolded.get(voice.casefold())
    if match is not None:
        return match

    supported = ", ".join(sorted(allowed))
    raise TimbreValidationError(
        f"Unsupported voice '{voice}'. Supported voices: {supported}."
    )


def resolve_voice(
    voice: str | None,
    language: str,
    model: str,
) -> str:
    """Resolve and validate a voice for the selected model and language."""

    if model == "timbre-v3.0":
        allowed: tuple[str, ...] | frozenset[str] = TIMBRE_V30_VOICES
        default_voice = V30_DEFAULT_VOICE
    elif model == "timbre-v2.5":
        allowed = V25_VOICES_BY_LANGUAGE[language]
        default_voice = allowed[0]
    else:  # Defensive: _resolve_model already rejects unknown models.
        raise ServiceNotConfiguredError(f"Unsupported TTS model '{model}'.")

    requested = (voice or "").strip()
    if not requested:
        return default_voice

    return _canonical_voice(requested, allowed)


def _parse_provider_body(body: str) -> dict[str, object]:
    try:
        parsed = json.loads(body)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _provider_message(body: dict[str, object]) -> str | None:
    """Extract only the provider's human-readable message for classification."""

    detail = body.get("detail")
    if isinstance(detail, dict):
        message = detail.get("message")
        if isinstance(message, str):
            return message
    if isinstance(detail, str):
        return detail

    message = body.get("message")
    if isinstance(message, str):
        return message

    error = body.get("error")
    if isinstance(error, dict):
        error_message = error.get("message")
        if isinstance(error_message, str):
            return error_message
    return None


def _provider_error_code(body: dict[str, object]) -> str | None:
    detail = body.get("detail")
    if isinstance(detail, dict):
        code = detail.get("error_code")
        if code is not None:
            return str(code)

    error = body.get("error")
    if isinstance(error, dict):
        code = error.get("type")
        if code is not None:
            return str(code)

    code = body.get("error_code")
    return str(code) if code is not None else None


def _looks_like_text_too_long(message: str | None) -> bool:
    if not message:
        return False
    lowered = message.casefold()
    markers = ("too long", "maximum length", "max length", "too many characters")
    return any(marker in lowered for marker in markers)


def _looks_like_no_audio(message: str | None) -> bool:
    if not message:
        return False
    lowered = message.casefold()
    return "no audio generated" in lowered or "no audio" in lowered


def _raise_for_api_error(exc: APIError) -> NoReturn:
    body = _parse_provider_body(exc.body)
    code = _provider_error_code(body)
    message = _provider_message(body)
    logger.warning(
        "Gnani Timbre TTS failed: status=%s error_code=%s",
        exc.status_code,
        code or "unknown",
    )

    status = exc.status_code

    if status in (400, 413, 422):
        raise TimbreValidationError(
            "The text-to-speech provider rejected the request. Check the text "
            "and language."
        ) from exc

    if status in (401, 402, 403):
        raise GnaniTimbreAuthError(
            "Text-to-speech provider rejected the configured credentials or the "
            "key lacks the TTS scope."
        ) from exc

    if status == 429:
        raise GnaniTimbreUnavailableError(
            "Text-to-speech provider is rate limiting requests. Try again shortly."
        ) from exc

    if status in (408, 504):
        raise GnaniTimbreTimeoutError(
            "Text-to-speech provider did not finish in time. Try again."
        ) from exc

    if status >= 500:
        if status == 500 and _looks_like_text_too_long(message):
            raise TimbreValidationError(
                "Text is too long for the text-to-speech provider. Shorten the "
                "text and try again."
            ) from exc
        if status == 500 and _looks_like_no_audio(message):
            raise GnaniTimbreError(
                "The text-to-speech provider could not generate audio for the "
                "supplied text and language. Confirm that Timbre is enabled for "
                "this language and voice on your Gnani account."
            ) from exc
        raise GnaniTimbreUnavailableError(
            "Text-to-speech provider is temporarily unavailable. Try again."
        ) from exc

    raise GnaniTimbreError("Text-to-speech provider returned an error.") from exc


def _validate_audio(audio: bytes) -> None:
    if not audio:
        raise GnaniTimbreError(
            "Text-to-speech provider returned an empty audio response."
        )
    if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise GnaniTimbreError(
            "Text-to-speech provider returned an unexpected audio format."
        )


def _normalize_wav_header(audio: bytes) -> bytes:
    """Repair placeholder RIFF/data sizes returned by the TTS provider.

    The provider returns a valid PCM WAV but leaves the RIFF and ``data`` chunk
    sizes set to ``0xFFFFFFFF``. Players that trust those sizes see a multi-hour
    file and may fail to play it. The provider places ``data`` last, so its real
    size is the number of bytes remaining after the data chunk header.
    """

    if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise GnaniTimbreError(
            "Text-to-speech provider returned an unexpected audio format."
        )

    buffer = bytearray(audio)
    offset = 12
    data_size_offset: int | None = None
    data_payload_offset: int | None = None

    while offset + 8 <= len(buffer):
        chunk_id = bytes(buffer[offset : offset + 4])
        chunk_size = struct.unpack_from("<I", buffer, offset + 4)[0]

        if chunk_id == b"data":
            data_size_offset = offset + 4
            data_payload_offset = offset + 8
            break

        # Chunks are word-aligned. Reject a chunk whose declared size would
        # run past the end of the response instead of reading out of bounds.
        next_offset = offset + 8 + chunk_size + (chunk_size & 1)
        if next_offset > len(buffer):
            raise GnaniTimbreError(
                "Text-to-speech provider returned an unexpected audio format."
            )
        offset = next_offset

    if data_size_offset is None or data_payload_offset is None:
        raise GnaniTimbreError(
            "Text-to-speech provider returned a WAV without audio data."
        )

    actual_data_size = len(buffer) - data_payload_offset
    if actual_data_size <= 0:
        raise GnaniTimbreError(
            "Text-to-speech provider returned a WAV without audio data."
        )

    struct.pack_into("<I", buffer, 4, len(buffer) - 8)
    struct.pack_into("<I", buffer, data_size_offset, actual_data_size)
    return bytes(buffer)


class GnaniTimbreService:
    """Async wrapper around the synchronous official Gnani TTS SDK client."""

    service_name = "Gnani Timbre (text-to-speech)"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def is_configured(self) -> bool:
        base_url = (
            self.settings.gnani_tts_base_url
            or self.settings.gnani_base_url
            or DEFAULT_BASE_URL
        )
        return bool(self.settings.gnani_api_key.strip() and base_url.strip())

    def _ensure_configured(self) -> None:
        if not self.is_configured:
            raise ServiceNotConfiguredError(
                f"{self.service_name} is not configured. Set GNANI_API_KEY in "
                "backend/.env."
            )

    def _build_client(self) -> GnaniTTSClient:
        self._ensure_configured()

        base_url = (
            self.settings.gnani_tts_base_url
            or self.settings.gnani_base_url
            or DEFAULT_BASE_URL
        ).strip().rstrip("/")
        timeout = max(1.0, float(self.settings.gnani_tts_timeout_seconds))

        try:
            return GnaniTTSClient(
                api_key=self.settings.gnani_api_key.strip(),
                base_url=base_url,
                timeout=timeout,
            )
        except AuthenticationError as exc:
            raise GnaniTimbreAuthError(
                "Text-to-speech provider authentication failed. Check "
                "GNANI_API_KEY."
            ) from exc

    async def synthesize(
        self,
        *,
        text: str,
        language: str = "en-IN",
        voice: str | None = None,
    ) -> SpeechResult:
        """Synthesize text and return the complete WAV audio response.

        The official SDK uses a synchronous ``requests`` client, so the network
        call is moved to a worker thread to avoid blocking FastAPI's event loop.
        """

        self._ensure_configured()
        normalized_text = validate_text(text)
        normalized_language = normalize_language(language)
        model = _resolve_model(self.settings)
        resolved_voice = resolve_voice(voice, normalized_language, model)
        client = self._build_client()

        try:
            audio = await asyncio.to_thread(
                client.synthesize,
                normalized_text,
                voice=resolved_voice,
                model=model,
                language=normalized_language,
                audio_config=AUDIO_CONFIG,
            )
        except APIError as exc:
            _raise_for_api_error(exc)
        except AuthenticationError as exc:
            raise GnaniTimbreAuthError(
                "Text-to-speech provider authentication failed. Check "
                "GNANI_API_KEY."
            ) from exc
        except requests_exceptions.Timeout as exc:
            logger.warning("Gnani Timbre TTS timed out")
            raise GnaniTimbreTimeoutError(
                "Text-to-speech service timed out. Try again."
            ) from exc
        except requests_exceptions.RequestException as exc:
            logger.warning(
                "Gnani Timbre TTS request failed: %s", type(exc).__name__
            )
            raise GnaniTimbreUnavailableError(
                "Text-to-speech service is unreachable. Try again."
            ) from exc
        except GnaniTTSError as exc:
            logger.warning(
                "Gnani Timbre TTS SDK error: %s", type(exc).__name__
            )
            raise GnaniTimbreError(
                "Text-to-speech service returned an error."
            ) from exc
        except ValueError as exc:
            # The SDK validates models/voices/languages locally. We validate the
            # same values before calling it, so this indicates a contract drift.
            logger.warning("Gnani Timbre TTS SDK validation failed")
            raise GnaniTimbreError(
                "Text-to-speech service configuration is invalid."
            ) from exc
        except Exception as exc:  # Network/protocol edge cases from the SDK.
            logger.exception(
                "Unexpected Gnani Timbre TTS failure: %s", type(exc).__name__
            )
            raise GnaniTimbreError(
                "Text-to-speech service returned an unexpected error."
            ) from exc

        _validate_audio(audio)
        audio = _normalize_wav_header(audio)
        return SpeechResult(
            audio=audio,
            content_type=CONTENT_TYPE,
            model=model,
            language=normalized_language,
            voice=resolved_voice,
        )


@lru_cache
def get_gnani_timbre_service() -> GnaniTimbreService:
    return GnaniTimbreService()
