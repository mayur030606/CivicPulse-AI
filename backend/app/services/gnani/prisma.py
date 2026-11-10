"""Gnani Prisma — speech-to-text.

The implementation lives in ``app.services.gnani_prisma`` (the module name used
by the voice route). This module re-exports it so the existing
``/api/v1/ai/transcribe`` route uses the same real Prisma v3.0 client instead of
the old 501 stub.
"""

from functools import lru_cache

from app.services.gnani_prisma import (
    GnaniPrismaService,
    TranscriptionResult,
    get_gnani_prisma_service,
)

PrismaService = GnaniPrismaService


@lru_cache
def get_prisma_service() -> GnaniPrismaService:
    return get_gnani_prisma_service()
