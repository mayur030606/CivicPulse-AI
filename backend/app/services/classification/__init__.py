"""Complaint classification services."""

from app.services.classification.base import (
    ClassificationProvider,
    ClassificationProviderError,
    ClassificationResult,
    ClassificationValidationError,
)
from app.services.classification.deterministic import (
    DeterministicClassificationProvider,
)
from app.services.classification.service import (
    ClassificationService,
    get_classification_provider,
    get_classification_service,
)

__all__ = [
    "ClassificationProvider",
    "ClassificationProviderError",
    "ClassificationResult",
    "ClassificationService",
    "ClassificationValidationError",
    "DeterministicClassificationProvider",
    "get_classification_provider",
    "get_classification_service",
]
