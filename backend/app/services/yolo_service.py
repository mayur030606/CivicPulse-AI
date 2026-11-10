"""YOLO image analysis.

The model is loaded lazily so the API starts quickly and works without the
heavy AI dependencies installed. Install them with:

    pip install -r requirements-ai.txt

Inference is CPU-bound and runs in a bounded AnyIO worker thread so it does not
block the async request event loop. The default ``yolov8n.pt`` model uses generic
COCO labels (person, car, truck, ...); it does not detect civic issues such as
potholes or illegal dumping unless a custom model is configured.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from typing import Any

import anyio
from anyio import CapacityLimiter

from app.core.config import Settings, get_settings
from app.services.errors import ServiceUnavailableError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Detection:
    label: str
    confidence: float
    box: list[float] | None = None


@lru_cache(maxsize=1)
def _load_model() -> Any:
    try:
        from ultralytics import YOLO
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise ServiceUnavailableError(
            "Ultralytics is not installed. Run: pip install -r requirements-ai.txt"
        ) from exc

    settings = get_settings()
    try:
        return YOLO(settings.yolo_model_path)
    except Exception as exc:
        # Missing weights, an invalid path, or an incompatible model must not
        # become an unhandled 500 or expose internal paths to the client.
        logger.warning("YOLO model could not be loaded: %s", type(exc).__name__)
        raise ServiceUnavailableError(
            "Image analysis model is unavailable. Install requirements-ai.txt "
            "and verify YOLO_MODEL_PATH."
        ) from exc


class YoloService:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        limiter: CapacityLimiter | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._limiter = limiter or CapacityLimiter(
            self._settings.yolo_max_concurrency
        )

    def analyze(self, image_bytes: bytes) -> list[Detection]:
        """Run inference synchronously (kept for direct callers and tests)."""

        return self._analyze_sync(image_bytes)

    async def analyze_async(self, image_bytes: bytes) -> list[Detection]:
        """Run inference off the event loop with bounded concurrency."""

        return await anyio.to_thread.run_sync(
            self._analyze_sync,
            image_bytes,
            limiter=self._limiter,
            abandon_on_cancel=True,
        )

    def _analyze_sync(self, image_bytes: bytes) -> list[Detection]:
        model = _load_model()

        try:
            from PIL import Image

            image = Image.open(BytesIO(image_bytes)).convert("RGB")
        except Exception as exc:
            raise ValueError("Uploaded file is not a readable image.") from exc

        try:
            results = model.predict(
                image,
                conf=self._settings.yolo_confidence,
                verbose=False,
            )
        except Exception as exc:
            logger.warning("YOLO inference failed: %s", type(exc).__name__)
            raise ServiceUnavailableError(
                "Image analysis is temporarily unavailable."
            ) from exc

        detections: list[Detection] = []
        for result in results:
            names = result.names or {}
            for box in result.boxes:
                class_id = int(box.cls[0].item())
                detections.append(
                    Detection(
                        label=names.get(class_id, str(class_id)),
                        confidence=round(float(box.conf[0].item()), 4),
                        box=[
                            round(float(value), 2)
                            for value in box.xyxy[0].tolist()
                        ],
                    )
                )
        return detections


@lru_cache
def get_yolo_service() -> YoloService:
    return YoloService()


def reset_yolo_service() -> None:
    """Clear cached model/service state (test and configuration helper)."""

    get_yolo_service.cache_clear()
    _load_model.cache_clear()
