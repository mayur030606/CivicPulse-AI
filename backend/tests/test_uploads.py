"""Upload hardening tests for Phase 3C-2C-2.

All files are synthetic. The tests never call Gnani, Ultralytics or any other
external provider, and the upload routes are exercised with the rate limiter
disabled so they stay deterministic.
"""

from __future__ import annotations

import asyncio
import io
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.testclient import TestClient
from PIL import Image

from app.core.uploads import (
    UploadBodyLimitMiddleware,
    UploadTooLargeError,
    UploadValidationError,
    read_upload_limited,
)
from app.main import app
from app.services.errors import ServiceUnavailableError
from app.services.gnani_prisma import TranscriptionResult
from app.services.yolo_service import Detection, YoloService


def wav_bytes(duration_seconds: float = 1.0, sample_rate: int = 8000) -> bytes:
    """Build a small, valid mono WAV file for validation tests."""

    frames = int(sample_rate * duration_seconds)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(1)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x80" * frames)
    return buffer.getvalue()


def image_bytes(
    image_format: str = "PNG",
    size: tuple[int, int] = (32, 32),
) -> bytes:
    """Build a small, valid image for validation tests."""

    buffer = io.BytesIO()
    Image.new("RGB", size, (20, 120, 220)).save(buffer, format=image_format)
    return buffer.getvalue()


class FakeUpload:
    """Minimal UploadFile stand-in that records whether it was closed."""

    filename = "clip.wav"
    content_type = "audio/wav"

    def __init__(self, chunks: list[bytes], error: BaseException | None = None):
        self._chunks = list(chunks)
        self._error = error
        self.closed = False

    async def read(self, _size: int) -> bytes:
        if self._error is not None:
            raise self._error
        return self._chunks.pop(0) if self._chunks else b""

    async def close(self) -> None:
        self.closed = True


class UploadReaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_returns_bytes_and_closes_upload(self) -> None:
        upload = FakeUpload([b"abc", b"def"])

        result = await read_upload_limited(upload, max_bytes=10, kind="Audio file")

        self.assertEqual(result.data, b"abcdef")
        self.assertEqual(result.size, 6)
        self.assertEqual(result.filename, "clip.wav")
        self.assertEqual(result.content_type, "audio/wav")
        self.assertTrue(upload.closed)

    async def test_oversized_upload_raises_and_closes_upload(self) -> None:
        upload = FakeUpload([b"abcdef"])

        with self.assertRaises(UploadTooLargeError):
            await read_upload_limited(upload, max_bytes=5, kind="Audio file")

        self.assertTrue(upload.closed)

    async def test_empty_upload_raises_and_closes_upload(self) -> None:
        upload = FakeUpload([])

        with self.assertRaises(UploadValidationError):
            await read_upload_limited(upload, max_bytes=5, kind="Audio file")

        self.assertTrue(upload.closed)

    async def test_cancellation_closes_upload(self) -> None:
        upload = FakeUpload([], error=asyncio.CancelledError())

        with self.assertRaises(asyncio.CancelledError):
            await read_upload_limited(upload, max_bytes=5, kind="Audio file")

        self.assertTrue(upload.closed)


class UploadBodyLimitMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_declared_oversized_body_is_rejected_before_app(self) -> None:
        called = False

        async def inner_app(_scope, _receive, _send) -> None:
            nonlocal called
            called = True

        middleware = UploadBodyLimitMiddleware(inner_app, limits={"/upload": 10})
        messages: list[dict] = []

        async def send(message: dict) -> None:
            messages.append(message)

        async def receive() -> dict:
            return {"type": "http.request", "body": b""}

        scope = {
            "type": "http",
            "path": "/upload",
            "headers": [(b"content-length", b"11")],
        }

        await middleware(scope, receive, send)

        self.assertFalse(called)
        self.assertEqual(messages[0]["status"], 413)

    async def test_missing_content_length_reaches_app(self) -> None:
        called = False

        async def inner_app(_scope, _receive, _send) -> None:
            nonlocal called
            called = True

        middleware = UploadBodyLimitMiddleware(inner_app, limits={"/upload": 10})

        async def send(_message: dict) -> None:
            return None

        async def receive() -> dict:
            return {"type": "http.request", "body": b""}

        await middleware(
            {"type": "http", "path": "/upload", "headers": []},
            receive,
            send,
        )

        self.assertTrue(called)

    def test_chunked_body_without_content_length_returns_413(self) -> None:
        test_app = FastAPI()
        test_app.add_middleware(
            UploadBodyLimitMiddleware,
            limits={"/upload": 5},
        )

        @test_app.post("/upload")
        async def upload(request: Request) -> dict[str, bool]:
            await request.body()
            return {"ok": True}

        response = TestClient(test_app).post(
            "/upload",
            content=iter([b"123", b"456"]),
        )

        self.assertEqual(response.status_code, 413)
        self.assertIn("too large", response.json()["detail"].lower())

    def test_chunked_multipart_upload_returns_413(self) -> None:
        test_app = FastAPI()
        test_app.add_middleware(
            UploadBodyLimitMiddleware,
            limits={"/upload": 100},
        )

        @test_app.post("/upload")
        async def upload(file: UploadFile = File(...)) -> dict[str, int]:
            return {"size": len(await file.read())}

        boundary = "----civicpulse-test-boundary"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="x.bin"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + (b"x" * 200) + f"\r\n--{boundary}--\r\n".encode()

        response = TestClient(test_app).post(
            "/upload",
            content=iter([body[:60], body[60:]]),
            headers={
                "content-type": f"multipart/form-data; boundary={boundary}"
            },
        )

        self.assertEqual(response.status_code, 413)
        self.assertIn("too large", response.json()["detail"].lower())


class UploadRouteTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._limiter_patch = patch(
            "app.core.rate_limit.get_rate_limiter", return_value=None
        )
        self._limiter_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self._limiter_patch.stop()


class AudioUploadRouteTests(UploadRouteTestBase):
    def test_valid_audio_upload_reaches_provider(self) -> None:
        audio = wav_bytes()
        fake_service = SimpleNamespace(
            transcribe=AsyncMock(
                return_value=TranscriptionResult(
                    transcript="hello",
                    detected_language_code="en-IN",
                    model="prisma-v3.0",
                )
            )
        )

        with patch(
            "app.routes.voice.get_gnani_prisma_service",
            return_value=fake_service,
        ):
            response = self.client.post(
                "/api/v1/voice/transcribe",
                files={"audio_file": ("clip.wav", audio, "audio/wav")},
                data={"language_code": "en-IN"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["transcript"], "hello")
        fake_service.transcribe.assert_awaited_once()
        kwargs = fake_service.transcribe.await_args.kwargs
        self.assertEqual(kwargs["audio"], audio)
        self.assertEqual(kwargs["filename"], "clip.wav")
        self.assertEqual(kwargs["content_type"], "audio/wav")
        self.assertEqual(kwargs["language_code"], "en-IN")

    def test_audio_exceeding_10_mb_is_rejected(self) -> None:
        oversized = b"x" * (10 * 1024 * 1024 + 1)
        fake_service = SimpleNamespace(transcribe=AsyncMock())

        with patch(
            "app.routes.voice.get_gnani_prisma_service",
            return_value=fake_service,
        ):
            response = self.client.post(
                "/api/v1/voice/transcribe",
                files={"audio_file": ("clip.wav", oversized, "audio/wav")},
            )

        self.assertEqual(response.status_code, 413)
        self.assertIn("too large", response.json()["detail"].lower())
        fake_service.transcribe.assert_not_awaited()

    def test_audio_longer_than_30_seconds_is_rejected(self) -> None:
        fake_service = SimpleNamespace(transcribe=AsyncMock())

        with patch(
            "app.routes.voice.get_gnani_prisma_service",
            return_value=fake_service,
        ):
            response = self.client.post(
                "/api/v1/voice/transcribe",
                files={
                    "audio_file": (
                        "long.wav",
                        wav_bytes(31.0),
                        "audio/wav",
                    )
                },
            )

        self.assertEqual(response.status_code, 422)
        self.assertIn("30 seconds", response.json()["detail"])
        fake_service.transcribe.assert_not_awaited()

    def test_invalid_audio_content_is_rejected(self) -> None:
        fake_service = SimpleNamespace(transcribe=AsyncMock())

        with patch(
            "app.routes.voice.get_gnani_prisma_service",
            return_value=fake_service,
        ):
            response = self.client.post(
                "/api/v1/voice/transcribe",
                files={"audio_file": ("bad.wav", b"not audio", "audio/wav")},
            )

        self.assertEqual(response.status_code, 422)
        fake_service.transcribe.assert_not_awaited()

    def test_unsupported_audio_format_is_rejected(self) -> None:
        fake_service = SimpleNamespace(transcribe=AsyncMock())

        with patch(
            "app.routes.voice.get_gnani_prisma_service",
            return_value=fake_service,
        ):
            response = self.client.post(
                "/api/v1/voice/transcribe",
                files={"audio_file": ("clip.txt", b"text", "text/plain")},
            )

        self.assertEqual(response.status_code, 415)
        fake_service.transcribe.assert_not_awaited()

    def test_legacy_ai_transcribe_uses_same_validation(self) -> None:
        fake_service = SimpleNamespace(transcribe=AsyncMock())

        with patch(
            "app.routes.ai.get_prisma_service",
            return_value=fake_service,
        ):
            response = self.client.post(
                "/api/v1/ai/transcribe",
                files={"file": ("bad.wav", b"not audio", "audio/wav")},
            )

        self.assertEqual(response.status_code, 422)
        fake_service.transcribe.assert_not_awaited()

    def test_legacy_ai_transcribe_valid_upload(self) -> None:
        fake_service = SimpleNamespace(
            transcribe=AsyncMock(
                return_value=TranscriptionResult(
                    transcript="hello",
                    detected_language_code="en-IN",
                )
            )
        )

        with patch(
            "app.routes.ai.get_prisma_service",
            return_value=fake_service,
        ):
            response = self.client.post(
                "/api/v1/ai/transcribe",
                files={"file": ("clip.wav", wav_bytes(), "audio/wav")},
                data={"language": "en-IN"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"text": "hello", "language": "en-IN"}
        )
        fake_service.transcribe.assert_awaited_once()


class ImageUploadRouteTests(UploadRouteTestBase):
    def test_valid_image_upload_reaches_yolo(self) -> None:
        fake_service = SimpleNamespace(
            analyze_async=AsyncMock(
                return_value=[
                    Detection(
                        label="car",
                        confidence=0.91,
                        box=[1.0, 2.0, 3.0, 4.0],
                    )
                ]
            )
        )

        with patch(
            "app.routes.ai.get_yolo_service",
            return_value=fake_service,
        ):
            response = self.client.post(
                "/api/v1/ai/analyze-image",
                files={
                    "file": (
                        "photo.png",
                        image_bytes("PNG"),
                        "image/png",
                    )
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "detections": [
                    {
                        "label": "car",
                        "confidence": 0.91,
                        "box": [1.0, 2.0, 3.0, 4.0],
                    }
                ]
            },
        )
        fake_service.analyze_async.assert_awaited_once()

    def test_oversized_image_is_rejected(self) -> None:
        settings = SimpleNamespace(
            yolo_max_upload_mb=1,
            yolo_max_image_width=8192,
            yolo_max_image_height=8192,
            yolo_max_image_pixels=25_000_000,
        )
        fake_service = SimpleNamespace(analyze_async=AsyncMock())

        with (
            patch("app.routes.ai.get_settings", return_value=settings),
            patch(
                "app.routes.ai.get_yolo_service",
                return_value=fake_service,
            ),
        ):
            response = self.client.post(
                "/api/v1/ai/analyze-image",
                files={
                    "file": (
                        "large.png",
                        b"x" * (1024 * 1024 + 1),
                        "image/png",
                    )
                },
            )

        self.assertEqual(response.status_code, 413)
        fake_service.analyze_async.assert_not_awaited()

    def test_invalid_image_content_is_rejected(self) -> None:
        fake_service = SimpleNamespace(analyze_async=AsyncMock())

        with patch(
            "app.routes.ai.get_yolo_service",
            return_value=fake_service,
        ):
            response = self.client.post(
                "/api/v1/ai/analyze-image",
                files={"file": ("bad.png", b"not an image", "image/png")},
            )

        self.assertEqual(response.status_code, 422)
        fake_service.analyze_async.assert_not_awaited()

    def test_excessive_image_width_is_rejected(self) -> None:
        settings = SimpleNamespace(
            yolo_max_upload_mb=10,
            yolo_max_image_width=16,
            yolo_max_image_height=100,
            yolo_max_image_pixels=10_000,
        )
        fake_service = SimpleNamespace(analyze_async=AsyncMock())

        with (
            patch("app.routes.ai.get_settings", return_value=settings),
            patch(
                "app.routes.ai.get_yolo_service",
                return_value=fake_service,
            ),
        ):
            response = self.client.post(
                "/api/v1/ai/analyze-image",
                files={
                    "file": (
                        "wide.png",
                        image_bytes("PNG", (32, 8)),
                        "image/png",
                    )
                },
            )

        self.assertEqual(response.status_code, 422)
        fake_service.analyze_async.assert_not_awaited()

    def test_excessive_image_pixels_is_rejected(self) -> None:
        settings = SimpleNamespace(
            yolo_max_upload_mb=10,
            yolo_max_image_width=100,
            yolo_max_image_height=100,
            yolo_max_image_pixels=100,
        )
        fake_service = SimpleNamespace(analyze_async=AsyncMock())

        with (
            patch("app.routes.ai.get_settings", return_value=settings),
            patch(
                "app.routes.ai.get_yolo_service",
                return_value=fake_service,
            ),
        ):
            response = self.client.post(
                "/api/v1/ai/analyze-image",
                files={
                    "file": (
                        "many-pixels.png",
                        image_bytes("PNG", (32, 32)),
                        "image/png",
                    )
                },
            )

        self.assertEqual(response.status_code, 422)
        fake_service.analyze_async.assert_not_awaited()

    def test_unsupported_image_format_is_rejected(self) -> None:
        fake_service = SimpleNamespace(analyze_async=AsyncMock())

        with patch(
            "app.routes.ai.get_yolo_service",
            return_value=fake_service,
        ):
            response = self.client.post(
                "/api/v1/ai/analyze-image",
                files={
                    "file": (
                        "photo.gif",
                        image_bytes("GIF"),
                        "image/gif",
                    )
                },
            )

        self.assertEqual(response.status_code, 415)
        fake_service.analyze_async.assert_not_awaited()

    def test_missing_yolo_dependencies_return_503(self) -> None:
        settings = SimpleNamespace(
            yolo_confidence=0.35,
            yolo_max_concurrency=2,
        )
        service = YoloService(settings=settings)

        with (
            patch(
                "app.routes.ai.get_yolo_service",
                return_value=service,
            ),
            patch(
                "app.services.yolo_service._load_model",
                side_effect=ServiceUnavailableError(
                    "Ultralytics is not installed."
                ),
            ),
        ):
            response = self.client.post(
                "/api/v1/ai/analyze-image",
                files={
                    "file": (
                        "photo.png",
                        image_bytes("PNG"),
                        "image/png",
                    )
                },
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("Ultralytics", response.json()["detail"])
