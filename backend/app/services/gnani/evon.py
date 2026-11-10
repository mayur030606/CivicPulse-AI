"""Gnani Evon — complaint understanding (NLU).

Contract status: NOT IMPLEMENTED. See docs/ai-integration.md.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.models.enums import Priority
from app.services.gnani.base import GnaniClient


@dataclass(slots=True)
class ComplaintUnderstanding:
    summary: str
    category: str
    priority: Priority
    language: str | None = None
    location_hint: str | None = None
    confidence: float | None = None
    raw: dict[str, Any] | None = None


class EvonService(GnaniClient):
    service_name = "Gnani Evon (complaint understanding)"

    async def understand(
        self, *, text: str, language: str | None = None
    ) -> ComplaintUnderstanding:
        """Extract structured complaint fields from free text.

        TODO: call Evon with the official request format and map the response
        (summary, category, priority, location hints) into ComplaintUnderstanding.
        """
        self._ensure_configured()
        raise NotImplementedError(
            "Gnani Evon complaint understanding is not implemented yet. Add the "
            "official endpoint, auth and payload format in app/services/gnani/evon.py."
        )


@lru_cache
def get_evon_service() -> EvonService:
    return EvonService()
