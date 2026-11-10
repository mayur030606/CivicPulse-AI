"""Provider abstraction for complaint classification.

Phase 1 uses the deterministic provider. A future Evon or LLM adapter should
implement ``ClassificationProvider`` and be selected in the service factory
without changing the public API contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models.enums import ComplaintCategory, Priority, Severity


class ClassificationError(RuntimeError):
    """Base class for classification-layer failures."""


class ClassificationValidationError(ClassificationError):
    """Raised when the complaint request is empty or contains unsupported data."""


class ClassificationProviderError(ClassificationError):
    """Raised when a provider fails or returns an unusable result."""


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    """Normalized result returned by any classification provider."""

    provider: str
    summary: str
    description: str
    category: ComplaintCategory
    severity: Severity
    priority: Priority
    responsible_department: str
    language: str | None
    location_hint: str | None
    matched_keywords: tuple[str, ...]
    severity_signals: tuple[str, ...]
    explanation: str
    needs_review: bool
    confidence: float | None = None


class ClassificationProvider(ABC):
    """Interface implemented by deterministic, Evon, or other providers."""

    name: str = "provider"

    @abstractmethod
    def classify(
        self, *, text: str, language: str | None = None
    ) -> ClassificationResult:
        """Classify complaint text and return a normalized result."""
