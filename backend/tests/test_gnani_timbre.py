import asyncio
import io
import struct
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import patch

from app.services.gnani_timbre import (
    GnaniTimbreError,
    GnaniTimbreService,
    _normalize_wav_header,
)

SAMPLE_RATE = 48000
CHANNELS = 1
SAMPLE_WIDTH = 2
PCM = struct.pack(
    "<8h",
    0,
    1000,
    -1000,
    32767,
    -32768,
    1234,
    -5678,
    42,
)


def build_placeholder_wav(pcm: bytes = PCM) -> bytes:
    """Build a provider-style WAV with 0xFFFFFFFF RIFF and data sizes."""

    block_align = CHANNELS * SAMPLE_WIDTH
    byte_rate = SAMPLE_RATE * block_align
    return (
        struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",
            0xFFFFFFFF,
            b"WAVE",
            b"fmt ",
            16,
            1,
            CHANNELS,
            SAMPLE_RATE,
            byte_rate,
            block_align,
            SAMPLE_WIDTH * 8,
            b"data",
            0xFFFFFFFF,
        )
        + pcm
    )


class NormalizeWavHeaderTests(unittest.TestCase):
    def test_repairs_placeholder_sizes_and_preserves_pcm(self) -> None:
        original = build_placeholder_wav()
        normalized = _normalize_wav_header(original)

        self.assertEqual(
            struct.unpack_from("<I", normalized, 4)[0], len(normalized) - 8
        )
        self.assertEqual(struct.unpack_from("<I", normalized, 40)[0], len(PCM))
        self.assertEqual(normalized[44:], PCM)
        # The fmt chunk header and payload must be untouched.
        self.assertEqual(normalized[12:36], original[12:36])

    def test_normalization_is_idempotent(self) -> None:
        once = _normalize_wav_header(build_placeholder_wav())
        twice = _normalize_wav_header(once)

        self.assertEqual(once, twice)

    def test_valid_wav_is_unchanged(self) -> None:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(SAMPLE_WIDTH)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(PCM)

        valid_wav = buffer.getvalue()
        self.assertEqual(_normalize_wav_header(valid_wav), valid_wav)

    def test_corrected_wav_parses_with_wave_module(self) -> None:
        normalized = _normalize_wav_header(build_placeholder_wav())

        with wave.open(io.BytesIO(normalized), "rb") as wav_file:
            self.assertEqual(wav_file.getnchannels(), CHANNELS)
            self.assertEqual(wav_file.getsampwidth(), SAMPLE_WIDTH)
            self.assertEqual(wav_file.getframerate(), SAMPLE_RATE)
            self.assertEqual(wav_file.getnframes(), len(PCM) // SAMPLE_WIDTH)
            self.assertEqual(
                wav_file.readframes(wav_file.getnframes()), PCM
            )

    def test_rejects_invalid_signatures(self) -> None:
        invalid_audio = (
            b"",
            b"RIFF",
            b"NOTARIFF....",
            b"RIFF\x00\x00\x00\x00NOPE",
        )

        for audio in invalid_audio:
            with self.subTest(audio=audio):
                with self.assertRaises(GnaniTimbreError):
                    _normalize_wav_header(audio)

    def test_rejects_missing_data_chunk(self) -> None:
        fmt_only = struct.pack(
            "<4sI4s4sIHHIIHH",
            b"RIFF",
            28,  # len(file) - 8
            b"WAVE",
            b"fmt ",
            16,
            1,
            CHANNELS,
            SAMPLE_RATE,
            SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH,
            CHANNELS * SAMPLE_WIDTH,
            SAMPLE_WIDTH * 8,
        )

        with self.assertRaises(GnaniTimbreError):
            _normalize_wav_header(fmt_only)

    def test_rejects_empty_data_chunk(self) -> None:
        with self.assertRaises(GnaniTimbreError):
            _normalize_wav_header(build_placeholder_wav(b""))

    def test_rejects_truncated_chunk_header(self) -> None:
        truncated = b"RIFF\x00\x00\x00\x00WAVE\x00\x00"

        with self.assertRaises(GnaniTimbreError):
            _normalize_wav_header(truncated)


class SynthesizeNormalizationTests(unittest.TestCase):
    def test_synthesize_returns_normalized_wav(self) -> None:
        settings = SimpleNamespace(
            gnani_api_key="test-key",
            gnani_tts_base_url="https://example.invalid",
            gnani_base_url=None,
            gnani_tts_timeout_seconds=10,
            gnani_tts_model="timbre-v2.5",
        )
        service = GnaniTimbreService(settings=settings)
        placeholder = build_placeholder_wav()
        calls: dict[str, object] = {}

        class FakeClient:
            def synthesize(self, text: str, **kwargs: object) -> bytes:
                calls["text"] = text
                calls.update(kwargs)
                return placeholder

        with patch.object(service, "_build_client", return_value=FakeClient()):
            result = asyncio.run(
                service.synthesize(text="Hello", language="en-IN")
            )

        self.assertEqual(
            struct.unpack_from("<I", result.audio, 4)[0], len(result.audio) - 8
        )
        self.assertEqual(struct.unpack_from("<I", result.audio, 40)[0], len(PCM))
        self.assertEqual(result.audio[44:], PCM)
        self.assertEqual(result.voice, "Kaveri")
        self.assertEqual(calls["text"], "Hello")
        self.assertEqual(calls["voice"], "Kaveri")
        self.assertEqual(calls["language"], "en-IN")
        self.assertEqual(calls["model"], "timbre-v2.5")


if __name__ == "__main__":
    unittest.main()
