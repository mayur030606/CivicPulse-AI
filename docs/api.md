# API Reference

Base URL (development): `http://127.0.0.1:8080/api/v1`

Interactive docs: <http://127.0.0.1:8080/docs>

## Conventions

- Request and response bodies are JSON unless noted.
- Errors use FastAPI's standard shape:

  ```json
  { "detail": "Incident not found." }
  ```

  Validation errors return `422` with a list in `detail`.
- Timestamps are ISO-8601 strings in UTC.
- Phase 3B-3 protects incident reads/updates, report summaries and admin
  overview with the Phase 3B-2 role dependencies. Public incident submission
  and tracking remain unauthenticated. Protected writes also require the
  `X-CSRF-Token` header. See [auth.md](auth.md) for the full matrix.

## Rate limiting

Public and provider-cost endpoints use a configurable per-client sliding-window
limiter. The check runs before the route handler. When a limit is exceeded the
API returns `429 Too Many Requests`:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 42
Cache-Control: no-store
```

```json
{ "detail": "Too many requests. Please try again later." }
```

`Retry-After` is an integer number of seconds. Successful requests do not include
rate-limit headers.

| Endpoint | Default limit | Window |
| --- | --- | --- |
| `POST /incidents` | 5 | 10 minutes |
| `GET /tracking/{tracking_id}` | 30 | 1 minute |
| `POST /auth/login` | 30 | 1 minute |
| `POST /voice/transcribe`, `POST /ai/transcribe` | 10 | 1 minute |
| `POST /voice/speak`, `POST /ai/speech` | 20 | 1 minute |
| `POST /ai/understand` | 30 | 1 minute |
| `POST /ai/analyze-image` | 10 | 1 minute |

All values are configurable through the `RATE_LIMIT_*` environment variables
documented in `.env.example`. The login limiter is per client IP and complements,
rather than replaces, the per-account failed-login lockout.

Client identity is the direct peer address. `X-Forwarded-For` and `X-Real-IP`
are used only when the direct peer is listed in `RATE_LIMIT_TRUSTED_PROXIES`
(comma-separated IPs/CIDRs). For a forwarded chain, the API walks from right to
left and skips trusted proxies, so an untrusted client cannot spoof the header.

The default `RATE_LIMIT_BACKEND=memory` backend is process-local and suitable for
development or one worker. Multi-worker deployments should install
`backend/requirements-redis.txt` and set `RATE_LIMIT_BACKEND=redis` with
`RATE_LIMIT_REDIS_URL`. If the shared backend is unavailable, protected
endpoints fail closed with a generic `503`; in production the app fails to start
when Redis is configured but unreachable. Rate-limit keys are hashed and raw IP
addresses are not logged.

## Authentication

See [auth.md](auth.md) for the full cookie/CSRF contract, migration and
bootstrap instructions.

### `POST /auth/login`

Authenticates with `{"email": "...", "password": "..."}` and sets:

- `civicpulse_session` — HttpOnly, SameSite=Lax (Secure in production)
- `civicpulse_csrf` — readable by the SPA for the `X-CSRF-Token` header

Invalid credentials, inactive accounts and locked accounts all return the same
`401` body: `{"detail": "Invalid email or password."}`. The response contains a
safe user profile, never a password hash or raw session token.

Login is also rate-limited per client IP (default 30 attempts per minute). A
`429` response includes `Retry-After`. This per-IP limiter is separate from the
per-account failed-login lockout, so a shared NAT cannot lock an account and an
attacker cannot use one IP to brute-force many accounts indefinitely.

### `GET /auth/me`

Returns the authenticated user's profile. Requires the session cookie.

### `POST /auth/logout`

Revokes the current server-side session and clears both cookies. Requires the
session cookie **and** the `X-CSRF-Token` header matching the CSRF cookie.

## Health

### `GET /health` (unversioned)

Liveness probe for containers and uptime checks:

```json
{ "status": "healthy" }
```

### `GET /api/v1/health`

Detailed service metadata:

```json
{
  "status": "ok",
  "service": "CivicPulse AI API",
  "version": "0.1.0",
  "environment": "development"
}
```

### `GET /api/v1/db-health`

Runs `SELECT 1` against MySQL to verify the connection:

```json
{ "status": "healthy", "database": "connected" }
```

Returns `503` with a generic message when the database is unreachable. The
connection URL, host, username and password are never returned.

### `GET /api/v1/health/db`

Backwards-compatible alias.

```json
{ "database": "ok" }
```

## Complaints (removed)

The legacy `/complaints` API was removed in Phase 3C-2A. It targeted a
`complaints` table that does not exist in the live MySQL schema, so every call
failed with a misleading database error. The paths are no longer registered and
return a plain `404 Not Found`:

| Method | Path | Response |
| --- | --- | --- |
| `POST` | `/complaints` | `404` (removed) |
| `GET` | `/complaints` | `404` (removed) |
| `GET` | `/complaints/{complaint_id}` | `404` (removed) |
| `PATCH` | `/complaints/{complaint_id}` | `404` (removed) |

Citizen reporting uses the incident workflow below. The SPA route `/complaints`
is a staff directory that already reads `/incidents`; only the legacy API paths
were removed.

## Incidents

These endpoints are the active citizen reporting workflow and are backed by the
existing `incidents` table.

### `POST /incidents`

**Public citizen submission.** No session or CSRF token is required. The only
accepted `status` value is `Submitted` (also the default); attempts to create an
incident in another workflow state return `422`. The endpoint is rate-limited to
5 submissions per client per 10 minutes by default.

```json
{
  "category": "accident",
  "description": "Two-wheeler collision; traffic is backing up.",
  "severity": "critical",
  "priority": "high",
  "status": "Submitted",
  "latitude": 23.0301,
  "longitude": 72.5802
}
```

Unknown JSON fields are rejected. The API always generates `tracking_id`
server-side (for example `CP-20261105-A1B2C3`); clients cannot supply or override
it, and sending `tracking_id` returns `422`. Response `201 Created`:

```json
{
  "id": 1,
  "tracking_id": "CP-20261105-A1B2C3",
  "category": "accident",
  "description": "Two-wheeler collision; traffic is backing up.",
  "severity": "critical",
  "priority": "high",
  "status": "Submitted",
  "latitude": 23.0301,
  "longitude": 72.5802,
  "created_at": "2026-11-05T09:40:00"
}
```

### `GET /incidents`

Requires an authenticated `dispatcher` or `admin` session (`401`/`403`).

| Name | Type | Default | Notes |
| --- | --- | --- | --- |
| `category` | string | — | Exact match |
| `status` | enum | — | `Submitted`, `In Progress`, `Resolved` or `Closed` |
| `severity` | string | — | Exact match |
| `priority` | string | — | Exact match |
| `limit` | int | 100 | 1–500 |
| `offset` | int | 0 | ≥ 0 |

### `GET /incidents/{incident_id}`

Requires an authenticated `dispatcher` or `admin` session. Returns one incident
or `404`.

### `PATCH /incidents/{incident_id}`

Requires an authenticated `dispatcher` or `admin` session **and** the
`X-CSRF-Token` header.

```json
{ "status": "In Progress", "severity": "high", "priority": "high" }
```

Only `category`, `description`, `severity`, `priority` and `status` are
mutable. Unknown fields, explicit `null` status and status strings outside the
allow-list (`Submitted`, `In Progress`, `Resolved`, `Closed`) return `422`.
A real status change appends a row to `status_history` with the old status, new
status and authenticated actor. Existing rows are never deleted or rewritten.

## AI endpoints

Prisma speech-to-text and Timbre text-to-speech are implemented. Evon NLU
remains a stub and returns `501`; YOLO returns `503` until `requirements-ai.txt`
is installed. These endpoints never return fabricated results.

### `POST /ai/transcribe`

Legacy alias of `/voice/transcribe` using the same Gnani Prisma v3.0 client.
`multipart/form-data`:

| Field | Type | Required |
| --- | --- | --- |
| `file` | audio file | yes |
| `language` | string | no |

Response:

```json
{ "text": "…", "language": "hi-IN" }
```

Both transcription routes now share the same bounded upload reader, 10 MB
default size cap, supported-format check and 30-second duration validation. The
legacy route still uses its original `file`/`language` fields; use
`POST /voice/transcribe` for the full Prisma response metadata and error
mapping.

### `POST /ai/understand`

```json
{ "text": "कचरा तीन दिन से नहीं उठाया गया", "language": "hi" }
```

Intended response:

```json
{
  "summary": "Garbage has not been collected for three days.",
  "category": "garbage",
  "priority": "high",
  "language": "hi",
  "location_hint": null,
  "confidence": 0.86
}
```

### `POST /ai/speech`

Legacy alias of `/voice/speak` using the same Gnani Timbre client.

```json
{ "text": "आपकी शिकायत दर्ज हो गई है।", "language": "hi" }
```

Response `200` is binary WAV audio with `Content-Type: audio/wav`. See
[`POST /voice/speak`](#post-voicespeak) for the full language/voice contract and
error mapping.

### `POST /ai/analyze-image`

`multipart/form-data` with one image file. The backend validates the actual
content with Pillow, not just the file extension or declared content type.

- Allowed formats: JPEG, PNG and WEBP.
- Maximum upload size: `YOLO_MAX_UPLOAD_MB` (10 MB default).
- Maximum dimensions: `YOLO_MAX_IMAGE_WIDTH` × `YOLO_MAX_IMAGE_HEIGHT`
  (8192 × 8192 default).
- Maximum total pixels: `YOLO_MAX_IMAGE_PIXELS` (25,000,000 default).
- Truncated, malformed and decompression-bomb images are rejected before
  inference.
- Inference runs in a bounded worker thread; at most `YOLO_MAX_CONCURRENCY`
  (2 default) YOLO calls run at once.

Example response:

```json
{
  "detections": [
    { "label": "car", "confidence": 0.91, "box": [112.0, 240.5, 388.2, 402.9] }
  ]
}
```

The default `yolov8n.pt` model uses **generic COCO labels** such as `person`,
`car` and `truck`. It does **not** detect civic issues such as potholes or
illegal dumping unless a custom model is configured. Labels in the response are
not civic-specific classifications.

Error mapping:

| HTTP | Cause |
| --- | --- |
| 413 | Upload exceeds `YOLO_MAX_UPLOAD_MB` or the request body is too large |
| 415 | Unsupported image content type or actual format |
| 422 | Empty, malformed/truncated image, or dimensions/pixels above the limit |
| 429 | Client exceeded the configured image-analysis rate limit |
| 503 | Ultralytics, the model weights or the configured model path is unavailable |

## Reports

Aggregate views for the dashboard. Individual incident intake stays at
`/incidents`.

### `GET /reports/summary`

Requires an authenticated `dispatcher` or `admin` session (`401`/`403`).
Returns incident totals grouped by status, priority, severity and category:

```json
{
  "total": 12,
  "by_status": [{ "value": "Submitted", "count": 7 }],
  "by_priority": [{ "value": "medium", "count": 8 }],
  "by_severity": [{ "value": "high", "count": 4 }],
  "by_category": [{ "value": "roads", "count": 5 }]
}
```

## Tracking

### `GET /tracking/{tracking_id}`

Public-safe status lookup by the incident tracking ID, for example
`CP-20261105-A1B2C3`. Returns `404` for unknown IDs; descriptions, citizen
reports and media paths are not exposed. Rate-limited to 30 lookups per client
per minute by default.

## Voice

### `GET /voice/status`

Reports whether Gnani credentials are configured. It never calls Gnani and
never fabricates a result:

```json
{
  "provider": "gnani",
  "credentials_configured": true,
  "integration_implemented": true,
  "message": "Gnani Prisma v3.0 speech-to-text is available at POST /api/v1/voice/transcribe and Gnani Timbre text-to-speech is available at POST /api/v1/voice/speak. Evon NLU remains unimplemented."
}
```

### `POST /voice/transcribe`

Transcribes a short clip with **Gnani Prisma v3.0** using the official REST
endpoint `https://api.vachana.ai/stt/v3`.

`multipart/form-data`:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `audio_file` | file | yes | WAV, MP3, OGG, FLAC, AAC or M4A; maximum 30 seconds |
| `language_code` | string | no | Defaults to `indic-auto`; or 1–4 codes such as `hi-IN,en-IN` |

The backend first validates the declared extension/content type, reads the
upload in bounded chunks, and parses the actual audio content with `mutagen` to
check its decoded duration. The default size cap is `GNANI_STT_MAX_UPLOAD_MB`
(10 MB) and the duration cap is 30 seconds. It then sends:

- Header `X-API-Key-ID: $GNANI_API_KEY` (server-side only)
- Form field `audio_file`
- Form field `model=prisma-v3.0`
- Form field `language_code=indic-auto` by default

Response `200` mirrors the documented Prisma v3.0 fields:

```json
{
  "success": true,
  "transcript": "मेरा खाता नंबर 12345 है",
  "detected_language_code": "hi-IN",
  "model": "prisma-v3.0",
  "request_id": "5c1f0a52-6d62-4e0b-9a38-2f2b8a8f7a10",
  "processing_time": 0.62,
  "end_to_end_latency": 0.71,
  "truncated": false
}
```

An empty `transcript` is a valid result when no speech is detected.
`detected_language_code` is omitted when Prisma has nothing to judge.

Error mapping:

| HTTP | Cause |
| --- | --- |
| 413 | Upload exceeds `GNANI_STT_MAX_UPLOAD_MB` |
| 415 | Unsupported extension/content type |
| 422 | Empty/corrupt audio, duration > 30 s, or invalid `language_code` |
| 429 | Client exceeded the configured voice/AI rate limit |
| 501 | `GNANI_API_KEY` is not configured |
| 502 | Gnani rejected credentials/scopes or returned an invalid/error response |
| 503 | Gnani is rate limiting or temporarily unavailable |
| 504 | Gnani did not respond within `GNANI_STT_TIMEOUT_SECONDS` |

The API key is never returned, logged, or included in error messages.

### `POST /voice/speak`

Synthesizes speech with **Gnani Timbre** using the official `gnani-vachana`
Python SDK and returns complete WAV audio in one response. This endpoint does
not stream or fabricate audio.

`application/json`:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `text` | string | yes | 1–5,000 characters; whitespace-only text is rejected |
| `language` | string | no | `en-IN` (default), `hi-IN` or `mr-IN`; aliases `en`, `English`, `hi`, `Hindi`, `mr`, `Marathi` are accepted |
| `voice` | string | no | Documented voice ID for the selected model/language; a language-appropriate default is used when omitted |

Examples:

```json
{ "text": "Your complaint has been registered successfully.", "language": "en-IN" }
```

```json
{ "text": "आपकी शिकायत सफलतापूर्वक दर्ज हो गई है।", "language": "hi-IN" }
```

```json
{ "text": "आपली तक्रार यशस्वीरित्या नोंदवली गेली आहे.", "language": "mr-IN" }
```

The default model is `timbre-v2.5`. Its documented preferred voices are:

| Language | Default voice | Other preferred voices |
| --- | --- | --- |
| `en-IN` | `Kaveri` | `Trupti`, `Devika`, `Pranav`, `Shlok`, `Girish` |
| `hi-IN` | `Nalini` | `Bhavna`, `Yashvi`, `Urmila`, `Jwala`, `Chitra`, `Ambuja`, `Deepak`, `Roopesh`, `Vikrant`, `Hemraj`, `Jalaj`, `Omkar` |
| `mr-IN` | `Zahira` | `Ishaan` |

With `GNANI_TTS_MODEL=timbre-v3.0`, any v3.0 voice (`Avinash`, `Shivani`,
`Lakshmi`, `Kalpana`, `Shubham`, `Prakash`, `Devansh`, `Yashraj`, `Chetana`,
`Vasudha`, `Riyaa`, `Tarika`, `Harshad`) can synthesize all three languages.
The default is `Shivani`.

Successful response `200`:

- `Content-Type: audio/wav`
- `Content-Disposition: inline; filename="speech.wav"`
- Binary WAV body (48 kHz, 16-bit mono) returned after verifying the RIFF/WAVE
  header

Error mapping:

| HTTP | Cause |
| --- | --- |
| 422 | Empty/blank text, text over 5,000 characters, unsupported language, invalid voice, or provider-rejected input |
| 429 | Client exceeded the configured voice/AI rate limit |
| 501 | `GNANI_API_KEY` is not configured |
| 502 | Gnani rejected credentials/scopes, could not generate audio for the language/voice, or returned an invalid response |
| 503 | Gnani is rate limiting or temporarily unavailable |
| 504 | Gnani did not respond within `GNANI_TTS_TIMEOUT_SECONDS` |

The API key is never returned, logged, or included in error messages.

## Admin

### `GET /admin/overview`

Requires an authenticated `admin` session. Dispatcher and viewer sessions
receive `403`. Read-only aggregate counts for `incidents`, `citizen_reports`,
`incident_images`, `status_history` and `departments`, plus configured service
status.

## Status codes

| Code | Meaning |
| --- | --- |
| 200 | Success |
| 201 | Resource created |
| 204 | Success with no body (logout) |
| 401 | Authentication required or invalid credentials |
| 403 | Insufficient role or CSRF validation failed |
| 404 | Resource not found |
| 409 | Database constraint violation |
| 413 | Uploaded audio exceeds the configured size limit |
| 415 | Unsupported media type |
| 422 | Validation error |
| 429 | Rate limit exceeded; retry after the `Retry-After` seconds |
| 501 | AI service not configured or not implemented (for example, Evon NLU) |
| 502 | Upstream AI provider rejected the request or credentials |
| 503 | Database, upstream AI service, optional AI dependency, or rate-limit backend unavailable |
| 504 | Upstream AI provider timed out |
