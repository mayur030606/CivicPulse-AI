"""Classification service orchestration and provider selection."""

from __future__ import annotations

from functools import lru_cache

from app.models.enums import ComplaintCategory, Severity
from app.services.classification.base import (
    ClassificationProvider,
    ClassificationProviderError,
    ClassificationResult,
)
from app.services.classification.deterministic import (
    DeterministicClassificationProvider,
)
from app.services.classification.taxonomy import normalize_language, normalize_text


class ClassificationService:
    """Validate a request, call the selected provider, and check its output."""

    def __init__(self, provider: ClassificationProvider) -> None:
        self._provider = provider

    @property
    def provider_name(self) -> str:
        return self._provider.name

    def classify(
        self, *, text: str, language: str | None = None
    ) -> ClassificationResult:
        clean_text = normalize_text(text)
        normalized_language = normalize_language(language)

        try:
            result = self._provider.classify(
                text=clean_text,
                language=normalized_language,
            )
        except (ClassificationProviderError, NotImplementedError):
            raise
        except Exception as exc:
            raise ClassificationProviderError(
                "The classification provider failed to process the complaint."
            ) from exc

        if not isinstance(result, ClassificationResult):
            raise ClassificationProviderError(
                "The classification provider returned an invalid result."
            )
        if not isinstance(result.category, ComplaintCategory):
            raise ClassificationProviderError(
                "The classification provider returned an unsupported category."
            )
        if not isinstance(result.severity, Severity):
            raise ClassificationProviderError(
                "The classification provider returned an unsupported severity."
            )

        return result


def get_classification_provider() -> ClassificationProvider:
    """Return the active provider.

    Phase 1 deliberately returns the deterministic provider. A future Evon or
    approved-LLM adapter should be selected here without changing routes or
    response schemas.
    """

    return DeterministicClassificationProvider()


@lru_cache
def get_classification_service() -> ClassificationService:
    return ClassificationService(provider=get_classification_provider())
