"""Bounded YOLO execution and optional-dependency tests."""

from __future__ import annotations

import asyncio
import sys
import threading
import time
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.errors import ServiceUnavailableError
from app.services.yolo_service import YoloService, _load_model


class YoloServiceExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_inference_runs_off_the_event_loop(self) -> None:
        service = YoloService(
            settings=SimpleNamespace(
                yolo_confidence=0.35,
                yolo_max_concurrency=2,
            )
        )

        def slow_inference(_image_bytes: bytes) -> list:
            time.sleep(0.25)
            return []

        service._analyze_sync = slow_inference  # type: ignore[method-assign]

        task = asyncio.create_task(service.analyze_async(b"image"))
        await asyncio.sleep(0.05)

        # If inference ran inline, the task would already be complete and the
        # sleep above could not have yielded control to this coroutine.
        self.assertFalse(task.done())
        self.assertEqual(await task, [])

    async def test_concurrent_inference_is_bounded(self) -> None:
        service = YoloService(
            settings=SimpleNamespace(
                yolo_confidence=0.35,
                yolo_max_concurrency=2,
            )
        )
        lock = threading.Lock()
        active = 0
        max_active = 0

        def tracked_inference(_image_bytes: bytes) -> list:
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.15)
            with lock:
                active -= 1
            return []

        service._analyze_sync = tracked_inference  # type: ignore[method-assign]

        await asyncio.gather(
            *(service.analyze_async(b"image") for _ in range(6))
        )

        self.assertLessEqual(max_active, 2)
        self.assertGreaterEqual(max_active, 2)


class YoloOptionalDependencyTests(unittest.TestCase):
    def tearDown(self) -> None:
        _load_model.cache_clear()

    def test_missing_ultralytics_returns_service_unavailable(self) -> None:
        _load_model.cache_clear()

        with patch.dict(sys.modules, {"ultralytics": None}):
            with self.assertRaises(ServiceUnavailableError):
                _load_model()

    def test_model_load_failure_does_not_expose_internal_details(self) -> None:
        fake_module = types.ModuleType("ultralytics")

        class FailingYolo:
            def __init__(self, _path: str) -> None:
                raise FileNotFoundError("secret internal model path")

        fake_module.YOLO = FailingYolo
        _load_model.cache_clear()

        with patch.dict(sys.modules, {"ultralytics": fake_module}):
            with self.assertRaises(ServiceUnavailableError) as context:
                _load_model()

        self.assertNotIn("secret internal model path", str(context.exception))
        self.assertIn("YOLO_MODEL_PATH", str(context.exception))
