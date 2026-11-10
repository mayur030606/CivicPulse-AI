# AI Integration Guide

## Current state

| Service | Purpose | File | Status |
| --- | --- | --- | --- |
| Gnani Prisma | Speech-to-text | `backend/app/services/gnani_prisma.py` | ✅ Implemented (`POST /voice/transcribe`) |
| Gnani Timbre | Text-to-speech | `backend/app/services/gnani_timbre.py` | ✅ Implemented (`POST /voice/speak`) |
| Gnani Evon | Complaint understanding | `backend/app/services/gnani/evon.py` | Stub → HTTP 501 |
| YOLO | Image analysis | `backend/app/services/yolo_service.py` | Optional deps → HTTP 503 |

Prisma and Timbre use the published Gnani contracts. Evon still has no confirmed
contract, so its stub remains and `services/gnani/base.py` deliberately stops
before making an HTTP call for it. No endpoint fabricates AI output.

## Why unimplemented services fail loudly

A scaffold that returns plausible-looking fake AI output is worse than one that
returns `501`: fake data silently flows into the database, dashboards and
citizen notifications. The remaining stub therefore:

1. Checks that `GNANI_BASE_URL` and `GNANI_API_KEY` are set.
2. Raises a typed error.
3. Lets `app/main.py` convert it to `501 Not Implemented` with an actionable
   message.

## Configuration

```env
GNANI_API_KEY=
GNANI_STT_URL=https://api.vachana.ai/stt/v3
GNANI_STT_MODEL=prisma-v3.0
GNANI_STT_LANGUAGE_CODE=indic-auto
GNANI_STT_TIMEOUT_SECONDS=60
GNANI_STT_MAX_UPLOAD_MB=10

# Timbre TTS
GNANI_TTS_BASE_URL=https://api.vachana.ai
GNANI_TTS_MODEL=timbre-v2.5
GNANI_TTS_TIMEOUT_SECONDS=60
```

`GNANI_API_KEY` is read by `app/core/config.py` from `backend/.env` (or the
repository-root `.env`) and is only used server-side in the `X-API-Key-ID`
header. It is never sent to the frontend, returned in a response, or written to
logs.

## Prisma v3.0 (implemented)

Official contract: <https://docs.gnani.ai/api/STT/speech-to-text>

- `POST https://api.vachana.ai/stt/v3`
- Header `X-API-Key-ID`
- Multipart field `audio_file`
- `model=prisma-v3.0`
- `language_code=indic-auto` by default (or 1–4 codes such as `hi-IN,en-IN`)
- Accepted formats: WAV, MP3, OGG, FLAC, AAC, M4A
- Maximum duration: 30 seconds

Implementation:

| Layer | File |
| --- | --- |
| Client + validation | `backend/app/services/gnani_prisma.py` |
| Route | `backend/app/routes/voice.py` |
| Response schema | `backend/app/schemas/voice.py` |

Request flow:

1. Validate the extension and declared content type.
2. Read the upload with a 10 MB cap (configurable).
3. Use `mutagen` to decode metadata and reject clips longer than 30 seconds.
4. Call Gnani with `audio_file`, `model=prisma-v3.0`, `language_code`, and the
   `X-API-Key-ID` header.
5. Return `success`, `transcript`, `detected_language_code`, `model`,
   `request_id`, timings and `truncated`.

Provider errors are mapped without leaking credentials:

| Provider condition | API result |
| --- | --- |
| Missing `GNANI_API_KEY` | `501` |
| 400 audio errors (`MAX_AUDIO_DURATION_EXCEEDED`, `EMPTY_AUDIO`, …) | `422` |
| 401/402/403 (key, credit, scope) | `502` |
| 429 / 5xx | `503` |
| Timeout / 504 | `504` |
| Other 400/422 | `502` |

An empty transcript is a valid result (for example, silence) and is returned as
`"transcript": ""`.

## Timbre (implemented)

Official contract: <https://docs.gnani.ai/api/TTS/tts-inference>
Voice catalog: <https://docs.gnani.ai/api/TTS/available-voices>
SDK: <https://github.com/Gnani-AI-Mintlify/gnani-vachana>

- SDK package: `gnani-vachana==0.9.0` (`pip install gnani-vachana`)
- `POST https://api.vachana.ai/api/v1/tts/inference`
- Header `X-API-Key-ID` (handled by `GnaniTTSClient`)
- `model=timbre-v2.5` by default; `timbre-v3.0` is configurable
- Request fields: `text`, `voice`, `model`, `language`, `speed`,
  `audio_config`
- Response: raw binary audio; this integration requests WAV
  (`audio/wav`, 48 kHz, 16-bit mono)

Implementation:

| Layer | File |
| --- | --- |
| SDK client, validation, error mapping | `backend/app/services/gnani_timbre.py` |
| Route | `backend/app/routes/voice.py` |
| Request schema | `backend/app/schemas/voice.py` |
| Legacy re-export | `backend/app/services/gnani/timbre.py` |

Request flow:

1. Validate and strip `text` (1–5,000 characters; blank text is rejected).
2. Normalize the requested language to `en-IN`, `hi-IN` or `mr-IN`.
3. Resolve a documented voice for the selected model and language.
4. Call the synchronous SDK in `asyncio.to_thread` so FastAPI's event loop is
   not blocked.
5. Verify that the provider returned a non-empty RIFF/WAVE payload.
6. Return the bytes as `audio/wav`.

Default Timbre v2.5 voices:

| Language | Default | Other documented voices |
| --- | --- | --- |
| `en-IN` | `Kaveri` | `Trupti`, `Devika`, `Pranav`, `Shlok`, `Girish` |
| `hi-IN` | `Nalini` | `Bhavna`, `Yashvi`, `Urmila`, `Jwala`, `Chitra`, `Ambuja`, `Deepak`, `Roopesh`, `Vikrant`, `Hemraj`, `Jalaj`, `Omkar` |
| `mr-IN` | `Zahira` | `Ishaan` |

Timbre v3.0 has its own catalog and every v3.0 voice supports all three
languages; the default is `Shivani`. Set `GNANI_TTS_MODEL=timbre-v3.0` to use
it. Voices cannot be shared between models.

Provider errors are mapped without leaking credentials:

| Provider condition | API result |
| --- | --- |
| Missing `GNANI_API_KEY` or invalid `GNANI_TTS_MODEL` | `501` |
| 400/413/422, text too long, or provider-rejected input | `422` |
| 401/402/403 (key, credit, scope) | `502` |
| 500 "No audio generated during synthesis" | `502` |
| 429 / other 5xx | `503` |
| Timeout / 408 / 504 | `504` |

The "No audio generated" message means Gnani accepted the request but produced
no audio. Confirm that Timbre is enabled for the requested language/voice on
your Gnani account and test the same text/voice in the Gnani playground.

## Remaining Evon contract checklist

Before implementing Evon, collect the following **from Gnani's official
documentation or onboarding contact**:

### Common

- [ ] Base URL per service (they may differ)
- [ ] Authentication scheme: header name, credential format, token lifetime
- [ ] Whether credentials are per-service or account-wide
- [ ] Rate limits, concurrency limits and quota behaviour
- [ ] Error response shape and retry semantics (which codes are retryable)
- [ ] Timeout guidance
- [ ] Data retention / PII handling requirements

### Evon (complaint understanding)

- [ ] Endpoint path and HTTP method
- [ ] Prompt / schema configuration model (if any)
- [ ] Request shape for free text and optional context
- [ ] Response shape for summary, category, priority, location hints
- [ ] How to constrain output to our category and priority enums
- [ ] Confidence semantics
- [ ] Language handling and supported languages

## Implementation pattern

1. Implement the confirmed contract in a dedicated service module such as
   `gnani_prisma.py` or `gnani_timbre.py` (auth header, timeout, error mapping).
2. Map the vendor response into a typed dataclass (`TranscriptionResult`,
   `SpeechResult`).
3. Keep public routes and Pydantic schemas as the stable contract; re-export the
   service from `app/services/gnani/` for legacy routes.
4. Run blocking SDK clients in a worker thread (`asyncio.to_thread`).
5. Add tests with recorded/sanitised responses; never commit real API keys.

Suggested error mapping:

| Vendor condition | Raise | HTTP result |
| --- | --- | --- |
| Missing credentials | `ServiceNotConfiguredError` | 501 |
| Contract not implemented | `NotImplementedError` | 501 |
| Timeout / upstream 5xx | `ServiceUnavailableError` or service-specific timeout/unavailable error | 503/504 |
| Invalid input (audio too long, unsupported language, blank text) | `ValueError` → route-level 422 | 422 |
| Rejected credentials/scope | Service-specific auth error | 502 |

> `ValueError` is not globally mapped; convert it to `HTTPException(422)` in the
> route if you introduce new validation.

## Media handling

The report form currently keeps selected files in the browser. Before calling
the AI endpoints:

1. Accept the upload in a route or a dedicated media route.
2. Enforce size and MIME limits **before** reading the whole file.
3. Persist to `backend/uploads/` (already created on startup) or object storage.
4. Store the path in `incident_images.image_path` and the transcript in
   `citizen_reports.transcript`, linked to the incident.
5. Pass bytes to the service; never expose storage paths to clients.

`backend/uploads/` is git-ignored.

## YOLO setup

YOLO is optional and excluded from the core requirements because it pulls
PyTorch.

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements-ai.txt
```

Configuration:

```env
YOLO_MODEL_PATH=yolov8n.pt
YOLO_CONFIDENCE=0.35
YOLO_MAX_UPLOAD_MB=10
YOLO_MAX_IMAGE_WIDTH=8192
YOLO_MAX_IMAGE_HEIGHT=8192
YOLO_MAX_IMAGE_PIXELS=25000000
YOLO_MAX_CONCURRENCY=2
```

Notes:

- `yolov8n.pt` is a generic COCO model. It will detect people, cars, trucks and
  similar objects, **not** civic issues such as potholes or illegal dumping.
  The API does not relabel generic detections as civic findings.
- For civic detection you need a custom dataset and a fine-tuned model. Point
  `YOLO_MODEL_PATH` at the resulting weights.
- The first run may download weights if the path is a model name and the file is
  not present locally. Set an absolute local path in offline environments.
- Uploads are validated as actual JPEG/PNG/WEBP content with Pillow. Size,
  width, height and total-pixel limits are enforced before decoding.
- Inference runs in a bounded AnyIO worker thread, so it does not block the
  request event loop. `YOLO_MAX_CONCURRENCY` caps simultaneous inference calls.
- Missing Ultralytics, missing weights or an unreadable model return `503`
  without exposing internal paths. The model is cached after the first load
  (`lru_cache`).

Test:

```bash
curl -X POST http://127.0.0.1:8080/api/v1/ai/analyze-image \
  -F "file=@photo.jpg"
```

Expected `200`:

```json
{
  "detections": [
    { "label": "car", "confidence": 0.94, "box": [12.0, 40.5, 220.8, 180.1] }
  ]
}
```

## Testing

Prisma (real request):

```bash
curl -X POST http://127.0.0.1:8080/api/v1/voice/transcribe \
  -F "audio_file=@recording.wav" \
  -F "language_code=indic-auto"
```

Expected `200` (the transcript may be empty when the clip has no speech):

```json
{
  "success": true,
  "transcript": "मेरा खाता नंबर 12345 है",
  "detected_language_code": "hi-IN",
  "model": "prisma-v3.0",
  "request_id": "…",
  "processing_time": 0.62,
  "end_to_end_latency": 0.71,
  "truncated": false
}
```

Timbre (real request):

```bash
curl -X POST http://127.0.0.1:8080/api/v1/voice/speak \
  -H "Content-Type: application/json" \
  -d '{"text":"Your complaint has been registered successfully.","language":"en-IN"}' \
  --output speech.wav
```

For Hindi or Marathi, change the body:

```json
{"text":"आपकी शिकायत सफलतापूर्वक दर्ज हो गई है।","language":"hi-IN"}
```

```json
{"text":"आपली तक्रार यशस्वीरित्या नोंदवली गेली आहे.","language":"mr-IN"}
```

Expected `200` with `Content-Type: audio/wav` and a playable RIFF/WAVE
`speech.wav`. The endpoint returns binary audio, not JSON.

Test in Swagger UI:

1. Set `GNANI_API_KEY` in `backend/.env` and start the API with
   `uvicorn app.main:app --reload --port 8080`.
2. Open <http://127.0.0.1:8080/docs>.
3. Expand **POST `/api/v1/voice/speak`** under the `voice` tag.
4. Click **Try it out**, replace the example with your text, choose `en-IN`,
   `hi-IN` or `mr-IN`, and click **Execute**.
5. A `200` response shows a **Download file** link for the WAV audio. Swagger UI
   does not usually play audio inline; download and open the file.
6. Use **GET `/api/v1/voice/status`** to confirm `credentials_configured` is
   `true` without calling Gnani.

If the provider returns `502` with "could not generate audio", confirm that
Timbre is enabled for that language/voice on your Gnani account.

Remaining stubs:

```bash
# 501 — Evon contract missing
curl -X POST http://127.0.0.1:8080/api/v1/ai/understand \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"garbage not collected\"}"

# 503 — Ultralytics not installed
curl -X POST http://127.0.0.1:8080/api/v1/ai/analyze-image \
  -F "file=@photo.jpg"
```

Provider contract tests should mock the external call so CI does not depend on
Gnani availability. Prisma can use `httpx.MockTransport`; Timbre can inject or
monkeypatch a fake SDK client or `asyncio.to_thread`. The `GNANI_API_KEY` must
not be present in test fixtures.

## Security checklist

- [ ] Keys only in `.env` / secret manager, never in `VITE_*` variables
- [ ] TLS verification enabled for outbound calls
- [ ] Request timeouts and bounded retries
- [ ] Upload size and MIME validation
- [ ] No raw audio/images retained longer than policy allows
- [ ] Logs redact transcripts and personal data where required
- [ ] Rate limiting on public AI endpoints
