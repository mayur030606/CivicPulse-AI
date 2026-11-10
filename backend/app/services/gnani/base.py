"""Shared plumbing for the remaining Gnani AI service.

Prisma STT and Timbre TTS use their own modules because their real contracts are
implemented. Evon still has no confirmed contract, so this base class
intentionally does not implement or guess endpoint paths, payloads or auth.

Until then, the service methods raise `NotImplementedError`, which the API maps
to HTTP 501 Not Implemented.
"""

from typing import Any

from app.core.config import Settings, get_settings
from app.services.errors import ServiceNotConfiguredError


class GnaniClient:
    """Base class holding configuration for a single Gnani service."""

    service_name = "Gnani"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.gnani_base_url and self.settings.gnani_api_key)

    def _ensure_configured(self) -> None:
        if not self.is_configured:
            raise ServiceNotConfiguredError(
                f"{self.service_name} is not configured. Set GNANI_BASE_URL and "
                "GNANI_API_KEY in .env, then implement the official API contract "
                "in backend/app/services/gnani/."
            )

    async def _post(self, path: str, **kwargs: Any) -> Any:
        """Send an authenticated POST request to Gnani.

        TODO: implement using httpx.AsyncClient once the official contract is
        known. The authentication header must match Gnani's documentation; do
        not assume a bearer token or API-key header here.
        """
        raise NotImplementedError(
            "Gnani API contract not implemented. Add the official endpoint path, "
            "authentication format and payload from Gnani's documentation."
        )
