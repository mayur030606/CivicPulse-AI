"""Shared, bounded handling for uploaded files.

FastAPI/Starlette spools multipart files to temporary storage before a route
runs. The helpers in this module enforce a byte cap while reading, close the
upload in every code path (success, validation error and cancellation), and
validate image content instead of trusting a file name or declared MIME type.

No uploaded bytes are logged here.
"""

from __future__ import annotations

import io
import logging
import warnings
from dataclasses import dataclass
from typing import Final

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import Settings

logger = logging.getLogger(__name__)

READ_CHUNK_SIZE: Final = 64 * 1024
UPLOAD_BODY_OVERHEAD_BYTES: Final = 1024 * 1024
BODY_TOO_LARGE_DETAIL: Final = (
    "Upload is too large. The request body exceeds the configured upload limit."
)

ALLOWED_IMAGE_FORMATS: Final = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
ALLOWED_IMAGE_CONTENT_TYPES: Final = {
    "image/jpeg",
    "image/jpg",
    "image/pjpeg",
    "image/png",
    "image/x-png",
    "image/webp",
    "application/octet-stream",
    "",
}
_IMAGE_FORMAT_LABEL = "JPEG, PNG or WEBP"


class UploadValidationError(ValueError):
    """Invalid upload content that should be reported to the client."""

    status_code = 422


class UploadTooLargeError(UploadValidationError):
    """The upload exceeds the configured byte cap."""

    status_code = 413


class UnsupportedUploadError(UploadValidationError):
    """The upload's declared type or actual format is not supported."""

    status_code = 415


@dataclass(frozen=True, slots=True)
class UploadedBytes:
    """Bounded upload bytes plus the metadata captured before closing the file."""

    data: bytes
    filename: str | None
    content_type: str | None
    size: int


@dataclass(frozen=True, slots=True)
class ValidatedImage:
    """An image whose actual format and dimensions have been validated."""

    data: bytes
    image_format: str
    content_type: str
    width: int
    height: int


def _megabytes(max_bytes: int) -> int:
    return max(1, max_bytes // (1024 * 1024))


async def read_upload_limited(
    upload: UploadFile,
    *,
    max_bytes: int,
    kind: str = "File",
) -> UploadedBytes:
    """Read an upload in bounded chunks and always close the temporary file.

    ``kind`` is only used in client-facing validation messages. The upload is
    closed in a ``finally`` block so cancellation and validation errors do not
    leave Starlette's spooled temporary file behind.
    """

    filename = upload.filename
    content_type = upload.content_type
    buffer = bytearray()

    try:
        while True:
            chunk = await upload.read(READ_CHUNK_SIZE)
            if not chunk:
                break

            if len(buffer) + len(chunk) > max_bytes:
                raise UploadTooLargeError(
                    f"{kind} is too large. The maximum upload size is "
                    f"{_megabytes(max_bytes)} MB."
                )
            buffer.extend(chunk)

        if not buffer:
            raise UploadValidationError(f"Uploaded {kind.lower()} is empty.")

        return UploadedBytes(
            data=bytes(buffer),
            filename=filename,
            content_type=content_type,
            size=len(buffer),
        )
    finally:
        try:
            await upload.close()
        except Exception:
            # Never include upload content or paths in the log.
            logger.warning("Failed to close an uploaded temporary file.")


def _normalised_content_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def validate_image_upload(upload: UploadedBytes, settings: Settings) -> ValidatedImage:
    """Validate actual image content, format and dimensions with Pillow.

    The dimension and pixel checks run before ``load()`` so a decompression bomb
    cannot force an unbounded decode. Pillow's own decompression-bomb warnings
    are converted to validation errors as an additional safeguard.
    """

    max_bytes = settings.yolo_max_upload_mb * 1024 * 1024
    if len(upload.data) > max_bytes:
        raise UploadTooLargeError(
            "Image is too large. The maximum upload size is "
            f"{_megabytes(max_bytes)} MB."
        )

    if not upload.data:
        raise UploadValidationError("Uploaded image is empty.")

    declared_type = _normalised_content_type(upload.content_type)
    if declared_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise UnsupportedUploadError(
            f"Unsupported image content type. Upload a {_IMAGE_FORMAT_LABEL} image."
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(upload.data)) as image:
                image_format = (image.format or "").upper()
                if image_format not in ALLOWED_IMAGE_FORMATS:
                    raise UnsupportedUploadError(
                        f"Unsupported image format. Upload a {_IMAGE_FORMAT_LABEL} image."
                    )

                width, height = image.size
                if width <= 0 or height <= 0:
                    raise UploadValidationError(
                        "The image has invalid dimensions."
                    )

                if (
                    width > settings.yolo_max_image_width
                    or height > settings.yolo_max_image_height
                    or width * height > settings.yolo_max_image_pixels
                ):
                    raise UploadValidationError(
                        "Image dimensions or pixel count exceed the allowed limit."
                    )

                # Fully decode after the bounded dimension checks. This rejects
                # truncated and malformed files before model inference starts.
                image.load()
    except UploadValidationError:
        raise
    except Image.DecompressionBombError as exc:
        raise UploadValidationError(
            "Image dimensions or pixel count exceed the allowed limit."
        ) from exc
    except Image.DecompressionBombWarning as exc:
        raise UploadValidationError(
            "Image dimensions or pixel count exceed the allowed limit."
        ) from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise UploadValidationError(
            f"Uploaded file is not a valid {_IMAGE_FORMAT_LABEL} image."
        ) from exc

    return ValidatedImage(
        data=upload.data,
        image_format=image_format,
        content_type=ALLOWED_IMAGE_FORMATS[image_format],
        width=width,
        height=height,
    )


def upload_body_limits(settings: Settings) -> dict[str, int]:
    """Return early ``Content-Length`` limits for multipart upload routes."""

    prefix = settings.api_v1_prefix.rstrip("/")
    audio_limit = settings.gnani_stt_max_upload_mb * 1024 * 1024
    image_limit = settings.yolo_max_upload_mb * 1024 * 1024
    return {
        f"{prefix}/voice/transcribe": audio_limit + UPLOAD_BODY_OVERHEAD_BYTES,
        f"{prefix}/ai/transcribe": audio_limit + UPLOAD_BODY_OVERHEAD_BYTES,
        f"{prefix}/ai/analyze-image": image_limit + UPLOAD_BODY_OVERHEAD_BYTES,
    }


class UploadBodyLimitMiddleware:
    """Reject oversized upload bodies before and during multipart parsing.

    A declared ``Content-Length`` above the limit is rejected immediately. The
    receive wrapper also counts streamed chunks, so chunked uploads or clients
    that understate ``Content-Length`` cannot force unbounded spooling. The
    route-level bounded read remains the authoritative per-file limit.
    """

    def __init__(self, app: ASGIApp, *, limits: dict[str, int]) -> None:
        self.app = app
        self._limits = {path.rstrip("/"): limit for path, limit in limits.items()}

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "").rstrip("/") or "/"
        limit = self._limits.get(path)
        if limit is None:
            await self.app(scope, receive, send)
            return

        raw_length = Headers(scope=scope).get("content-length")
        if raw_length is not None:
            try:
                content_length = int(raw_length)
            except ValueError:
                content_length = None
            if content_length is not None and content_length > limit:
                await self._reject(scope, receive, send)
                return

        received = 0

        async def limited_receive() -> dict:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # Raised while the multipart parser is consuming the body.
                    # FastAPI's exception middleware converts this to HTTP 413.
                    raise HTTPException(
                        status_code=413,
                        detail=BODY_TOO_LARGE_DETAIL,
                        headers={"Cache-Control": "no-store"},
                    )
            return message

        await self.app(scope, limited_receive, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content={"detail": BODY_TOO_LARGE_DETAIL},
            headers={"Cache-Control": "no-store"},
        )
        await response(scope, receive, send)
