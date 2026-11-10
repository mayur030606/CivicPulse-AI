"""Gnani Timbre — text-to-speech.

The implementation lives in ``app.services.gnani_timbre`` (the module name used
by the voice routes). This module re-exports it so the existing
``/api/v1/ai/speech`` route uses the same official SDK client instead of the old
501 stub.
"""

from functools import lru_cache

from app.services.gnani_timbre import (
    CONTENT_TYPE,
    DEFAULT_MODEL,
    MAX_TEXT_CHARS,
    GnaniTimbreAuthError,
    GnaniTimbreError,
    GnaniTimbreService,
    GnaniTimbreTimeoutError,
    GnaniTimbreUnavailableError,
    SpeechResult,
    TimbreValidationError,
    get_gnani_timbre_service,
)

TimbreService = GnaniTimbreService


@lru_cache
def get_timbre_service() -> GnaniTimbreService:
    return get_gnani_timbre_service()
