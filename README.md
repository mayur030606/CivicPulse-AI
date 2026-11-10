# CivicPulse AI

Multilingual civic complaint and traffic incident intelligence platform.

CivicPulse AI is designed to let residents report civic issues by **voice, text or photo** in their own language, and to give municipal teams structured, map-based intelligence. This repository currently contains the **project scaffold**: the full folder structure, the active incident reporting API, a React UI, and clearly marked integration points for the AI services.

> **Citizen reporting:** `/api/v1/incidents` and `/api/v1/tracking/{tracking_id}` are the active workflow. The legacy `/api/v1/complaints` API was removed in Phase 3C-2A because it targeted a `complaints` table that does not exist in the live database.

> **AI status:** **Gnani Prisma v3.0 speech-to-text is implemented** at `POST /api/v1/voice/transcribe` and **Gnani Timbre text-to-speech is implemented** at `POST /api/v1/voice/speak`. Both use the official Gnani contracts and require `GNANI_API_KEY`; TTS uses the official `gnani-vachana` Python SDK and returns WAV audio. Evon NLU remains a stub that returns `501 Not Implemented`. See [docs/ai-integration.md](docs/ai-integration.md).

---

## Stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19 + Vite + Tailwind CSS v4 |
| Routing | React Router |
| Maps | Leaflet + React Leaflet + OpenStreetMap tiles |
| HTTP client | Axios |
| Backend | Python FastAPI + Pydantic v2 |
| ORM | SQLAlchemy 2 |
| Database | MySQL (PyMySQL driver) |
| Speech-to-text | Gnani Prisma v3.0 — **implemented** |
| Complaint understanding | Gnani Evon — *stub* |
| Text-to-speech | Gnani Timbre — **implemented** (official SDK) |
| Image analysis | YOLO via Ultralytics — *optional install* |

---

## Project structure

```text
CivicPulse-AI/
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── api/                 # Axios client + endpoint wrappers
│   │   │   ├── client.js
│   │   │   ├── incidents.js
│   │   │   ├── ai.js
│   │   │   └── index.js
│   │   ├── components/
│   │   │   ├── complaints/      # ComplaintCard
│   │   │   ├── layout/          # Navbar, Footer, AppLayout
│   │   │   ├── map/             # IncidentMap (Leaflet)
│   │   │   └── ui/              # Button, Card, Badge, Spinner, …
│   │   ├── lib/                 # constants, formatters, demo data
│   │   ├── pages/               # Home, Report, Complaints, Map, Dashboard, 404
│   │   ├── App.jsx
│   │   ├── index.css            # Tailwind entry + civic theme
│   │   └── main.jsx
│   ├── index.html
│   ├── package.json
│   └── vite.config.js           # Tailwind plugin, /api dev proxy, envDir
│
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   └── config.py        # Pydantic settings (.env)
│   │   ├── database.py          # Engine, SessionLocal, Base, get_db
│   │   ├── init_db.py           # Create-missing-tables only (never drops)
│   │   ├── models/              # SQLAlchemy models matching MySQL tables
│   │   │   ├── citizen_report.py
│   │   │   ├── department.py
│   │   │   ├── incident.py
│   │   │   ├── incident_image.py
│   │   │   ├── status_history.py
│   │   │   ├── enums.py
│   │   │   └── mixins.py
│   │   ├── routes/              # FastAPI routers
│   │   │   ├── health.py
│   │   │   ├── incidents.py
│   │   │   ├── ai.py
│   │   │   ├── reports.py
│   │   │   ├── voice.py
│   │   │   ├── tracking.py
│   │   │   └── admin.py
│   │   ├── schemas/             # Pydantic request/response models
│   │   ├── services/            # Business + integration logic
│   │   │   ├── incidents.py
│   │   │   ├── yolo_service.py
│   │   │   ├── gnani_prisma.py  # Prisma v3.0 STT client + audio validation
│   │   │   ├── gnani_timbre.py  # Timbre TTS client (official Python SDK)
│   │   │   └── gnani/
│   │   │       ├── base.py      # Shared config for the remaining Evon stub
│   │   │       ├── prisma.py    # Re-exports gnani_prisma.py
│   │   │       ├── evon.py      # NLU stub
│   │   │       └── timbre.py    # Re-exports gnani_timbre.py
│   │   └── main.py              # App factory, CORS, error handlers
│   ├── requirements.txt
│   └── requirements-ai.txt      # Optional Ultralytics/YOLO install
│
├── docs/
│   ├── architecture.md
│   ├── api.md
│   └── ai-integration.md
│
├── .env.example                 # Shared by backend and frontend
├── .gitignore
└── README.md
```

---

## Prerequisites

- **Python** 3.11 or newer (developed on 3.13)
- **Node.js** 20.19+ or 22.12+ (developed on Node 25) and npm
- **MySQL** 8.0 or newer, running locally or reachable over the network
- Optional: a Gnani AI account and official API documentation
- Optional: YOLO weights / Ultralytics (see below)

---

## 1. Configure environment

From the repository root:

```powershell
Copy-Item .env.example .env
```

```bash
# macOS / Linux
cp .env.example .env
```

Then edit `.env`:

- Set `DATABASE_URL` to your full SQLAlchemy URL, for example
  `mysql+pymysql://USER:PASSWORD@localhost:3306/civicpulse`.
- `DB_HOST`, `DB_USER`, `DB_PASSWORD` and `DB_NAME` are used only when
  `DATABASE_URL` is absent.
- URL-encode special characters in the password (`@` becomes `%40`).
- Set `GNANI_API_KEY` to your Gnani key to enable Prisma speech-to-text and
  Timbre text-to-speech.
- `GNANI_STT_URL` defaults to `https://api.vachana.ai/stt/v3`;
  `GNANI_STT_MAX_UPLOAD_MB` defaults to `10` and
  `GNANI_STT_TIMEOUT_SECONDS` defaults to `60`.
- `GNANI_TTS_BASE_URL` defaults to `https://api.vachana.ai`,
  `GNANI_TTS_MODEL` defaults to `timbre-v2.5`, and
  `GNANI_TTS_TIMEOUT_SECONDS` defaults to `60`.
- Rate limiting is enabled by default. The `memory` backend is process-local and
  intended for development or a single worker. For multi-worker production,
  install `backend/requirements-redis.txt` and set
  `RATE_LIMIT_BACKEND=redis` with `RATE_LIMIT_REDIS_URL`.
- Set `RATE_LIMIT_TRUSTED_PROXIES` to your reverse proxy IPs/CIDRs before
  `X-Forwarded-For` or `X-Real-IP` is trusted. Leave it empty when there is no
  reverse proxy.
- `VITE_API_BASE_URL=/api/v1` works with the Vite dev proxy.

The backend reads the root `.env` and `backend/.env` (the backend file wins), and
Vite is configured with `envDir: '..'` so the frontend reads the shared root
file. `backend/.env` is gitignored — never commit real credentials.

---

## 2. Create the MySQL database

Run as a MySQL administrator:

```sql
CREATE DATABASE civicpulse
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER 'civicpulse'@'localhost' IDENTIFIED BY 'change-me';
GRANT ALL PRIVILEGES ON civicpulse.* TO 'civicpulse'@'localhost';
FLUSH PRIVILEGES;
```

Use the same password in `.env`. If you prefer the `root` account locally, set `DB_USER=root` and the matching `DB_PASSWORD`.

---

## 3. Run the backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Create missing tables only (safe: never drops or alters existing tables)
python -m app.init_db

# Start the API
uvicorn app.main:app --reload --port 8080
```

macOS / Linux activation:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.init_db
uvicorn app.main:app --reload --port 8080
```

- API root: <http://127.0.0.1:8080>
- Swagger UI: <http://127.0.0.1:8080/docs>
- ReDoc: <http://127.0.0.1:8080/redoc>
- Health: <http://127.0.0.1:8080/api/v1/health>
- Database health: <http://127.0.0.1:8080/api/v1/db-health>

> If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` for the current session, or call `.\.venv\Scripts\python.exe` directly.

---

## 4. Run the frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

Vite proxies `/api` to `http://127.0.0.1:8080`, so no CORS setup is needed in development. If the backend is on another host, set `VITE_API_BASE_URL` to its full `/api/v1` URL and add the frontend origin to `CORS_ORIGINS`.

Tests and production build:

```powershell
npm test        # Node test runner (api helpers, auth, route guards, view models)
npm run lint    # oxlint
npm run build
npm run preview
```

---

## Pages

| Route | Access | Purpose |
| --- | --- | --- |
| `/` | Public | Landing page and capability overview |
| `/report` | Public | Incident intake form with text, voice and photo support |
| `/tracking` | Public | Public-safe incident status lookup by tracking ID |
| `/login` | Public | Staff sign-in; redirects authenticated accounts to the dashboard |
| `/complaints` | Dispatcher / admin | Live incident list with category, status, severity and priority filters (legacy URL, backed by `/incidents`) |
| `/map` | Dispatcher / admin | Leaflet map built from live incidents with valid coordinates |
| `/dashboard` | Any authenticated staff role | Role-aware overview: admin aggregates, dispatcher report summary, viewer account details |
| `/incidents` | Dispatcher / admin | Incident management list with the same live filters |
| `/incidents/:incidentId` | Dispatcher / admin | Incident detail and canonical status workflow |

---

## What works today

| Area | Status |
| --- | --- |
| Project structure, env, docs | ✅ Complete |
| FastAPI app, CORS, OpenAPI docs | ✅ Working |
| Incident create / list / get / update | ✅ Requires MySQL; reads/updates need dispatcher/admin |
| MySQL models + table creation | ✅ `python -m app.init_db` (creates missing tables only) |
| Auth/schema migrations | ✅ `python -m alembic upgrade head` (auth tables + status-history actor) |
| React pages, routing, Tailwind theme | ✅ Working |
| Leaflet map | ✅ Demo markers (API wiring next) |
| Gnani Prisma (STT) | ✅ `POST /api/v1/voice/transcribe` (requires `GNANI_API_KEY`) |
| Gnani Evon (NLU) | ⏳ Stub → HTTP 501 |
| Gnani Timbre (TTS) | ✅ `POST /api/v1/voice/speak` (requires `GNANI_API_KEY`) |
| YOLO image analysis | ⏳ Optional install → HTTP 503 until installed |
| Auth foundation (login/logout/me, Argon2id, cookie sessions, CSRF, roles) | ✅ Phase 3B-2 |
| Admin/incident/report endpoint authorization | ✅ Phase 3B-3 |
| Rate limiting / abuse protection | ✅ Phase 3C-2C-1 (configurable; memory dev backend, optional Redis) |
| Legacy complaints API removal | ✅ Phase 3C-2A |
| Staff SPA: login, session restoration, logout, role-aware routes, dashboard, incident management | ✅ Phase 3B-4 |
| Notifications | ❌ Not started |

---

## YOLO (optional)

The core backend install intentionally excludes PyTorch. To enable image analysis:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements-ai.txt
```

`YOLO_MODEL_PATH` defaults to `yolov8n.pt`. On first use, Ultralytics may download the weights (internet required) unless you provide a local path. Then:

```bash
curl -X POST http://127.0.0.1:8080/api/v1/ai/analyze-image \
  -F "file=@photo.jpg"
```

Image uploads are limited to 10 MB, 8192×8192 dimensions and 25 million pixels by default; configure `YOLO_MAX_UPLOAD_MB`, `YOLO_MAX_IMAGE_WIDTH`, `YOLO_MAX_IMAGE_HEIGHT` and `YOLO_MAX_IMAGE_PIXELS` to change them. JPEG, PNG and WEBP are accepted and validated by content. Inference runs off the event loop with `YOLO_MAX_CONCURRENCY` (default 2) bounding simultaneous calls.

The default COCO model detects generic objects (people, cars, trucks, etc.); it does not detect potholes, garbage or other civic issues. A civic-issue model still needs to be trained or sourced.

---

## Gnani AI integration

Prisma speech-to-text is implemented in
`backend/app/services/gnani_prisma.py` and exposed at
`POST /api/v1/voice/transcribe` (legacy alias: `POST /api/v1/ai/transcribe`).
It uses the official contract:

- `POST https://api.vachana.ai/stt/v3`
- `X-API-Key-ID: $GNANI_API_KEY`
- multipart field `audio_file`
- `model=prisma-v3.0`
- `language_code=indic-auto` by default

The API validates WAV, MP3, OGG, FLAC, AAC and M4A uploads, enforces the 30
second provider limit with `mutagen`, caps uploads at 10 MB, and maps provider
authentication, API, rate-limit and timeout failures to HTTP errors. The API key
is never returned or logged.

Timbre text-to-speech is implemented in
`backend/app/services/gnani_timbre.py` with the official `gnani-vachana` SDK and
exposed at `POST /api/v1/voice/speak` (legacy alias: `POST /api/v1/ai/speech`).
It uses:

- `POST https://api.vachana.ai/api/v1/tts/inference`
- `X-API-Key-ID: $GNANI_API_KEY` (sent by the SDK)
- `model=timbre-v2.5` by default
- WAV output (`audio/wav`, 48 kHz, 16-bit mono)
- documented language-specific voices for `en-IN`, `hi-IN` and `mr-IN`

English uses `Kaveri`, Hindi uses `Nalini`, and Marathi uses `Zahira` by
default. An optional `voice` field can select another documented voice for the
selected model and language. `GNANI_TTS_MODEL=timbre-v3.0` is also supported;
its voices speak all three languages. The API validates text/language/voice,
runs the synchronous SDK call in a worker thread, verifies the returned
RIFF/WAVE payload, and maps provider failures to `422`/`502`/`503`/`504`.

Evon (NLU) remains a stub in `backend/app/services/gnani/evon.py` and returns
`501`. Full details: [docs/ai-integration.md](docs/ai-integration.md).

---

## API summary

Base path: `/api/v1`

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` (root) | Liveness probe → `{"status": "healthy"}` |
| GET | `/health` | Liveness (versioned) |
| GET | `/db-health` | MySQL connection test (`SELECT 1`) |
| GET | `/health/db` | Backwards-compatible database health alias |
| POST | `/auth/login` | Administrator login → HttpOnly session + CSRF cookies |
| GET | `/auth/me` | Current authenticated user (session cookie required) |
| POST | `/auth/logout` | Revoke current session (session cookie + `X-CSRF-Token`) |
| GET | `/reports/summary` | Incident aggregates (dispatcher/admin) |
| GET | `/tracking/{tracking_id}` | Public incident status lookup |
| GET | `/voice/status` | Voice integration configuration (no fake calls) |
| POST | `/voice/transcribe` | Gnani Prisma v3.0 speech-to-text (`audio_file`, `language_code`) |
| POST | `/voice/speak` | Gnani Timbre text-to-speech (`text`, `language`, optional `voice`) → WAV |
| GET | `/admin/overview` | Aggregate counts and service status (admin only) |
| POST | `/incidents` | Public incident creation (server-generated tracking ID; status `Submitted`; rate-limited) |
| GET | `/incidents` | List incidents (dispatcher/admin; `category`, `status`, `severity`, `priority`, `limit`, `offset`) |
| GET | `/incidents/{id}` | Get one incident (dispatcher/admin) |
| PATCH | `/incidents/{id}` | Update allowed fields (dispatcher/admin + CSRF; strict status allow-list) |
| POST | `/ai/transcribe` | Legacy alias of Gnani Prisma speech-to-text |
| POST | `/ai/understand` | Gnani Evon — 501 until implemented |
| POST | `/ai/speech` | Legacy alias of Gnani Timbre text-to-speech |
| POST | `/ai/analyze-image` | YOLO — 503 until `requirements-ai.txt` is installed |

Public incident creation, tracking lookup, login, and provider-cost voice/AI
endpoints are rate-limited and return `429` with `Retry-After` when a limit is
exceeded. See [docs/api.md](docs/api.md) for the configurable limits.

Details and examples: [docs/api.md](docs/api.md). Authentication setup:
[docs/auth.md](docs/auth.md).

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Could not load incidents` in the UI | Start FastAPI on port 8080 and ensure MySQL is running; check `/api/v1/db-health`. |
| `/api/v1/complaints` returns `404` | Expected: the legacy complaints API was removed in Phase 3C-2A. Use `/api/v1/incidents` and `/api/v1/tracking/{tracking_id}`. |
| `Access denied for user` | Set a valid `DATABASE_URL` in `backend/.env`; URL-encode special characters in the password. |
| `Unknown database 'civicpulse'` | Create the database, then run `python -m app.init_db` (creates missing tables only). |
| `Table 'civicpulse.users' doesn't exist` | From `backend/`, run `.\.venv\Scripts\python.exe -m alembic upgrade head`, then create the first admin with `python -m app.cli create-admin --email ...`. |
| CORS error in the browser | Use the Vite dev server (proxy), or add the origin to `CORS_ORIGINS`. |
| `Address already in use` | Stop the other process or run `uvicorn ... --port 8081` and update the Vite proxy. |
| `/voice/transcribe` returns 501 | Set `GNANI_API_KEY` in `backend/.env` and restart the API. |
| `/voice/transcribe` returns 502/503/504 | Check the Gnani key/scopes, rate limits and network; see `docs/api.md` for the mapping. |
| `/voice/speak` returns 501 | Set `GNANI_API_KEY` in `backend/.env` and restart the API. |
| `/voice/speak` returns 502 with "could not generate audio" | Confirm Timbre is enabled for that language/voice on your Gnani account. |
| `/voice/speak` returns 502/503/504 | Check the Gnani key/scopes, rate limits and network; see `docs/api.md` for the mapping. |
| Other AI endpoints return 501 | Expected — Evon is still a stub. |
| `/ai/analyze-image` returns 503 | Install `requirements-ai.txt`. |
| Public endpoints return `429` | Wait for the `Retry-After` seconds, or adjust the matching `RATE_LIMIT_*` limit/window. Behind a proxy, set `RATE_LIMIT_TRUSTED_PROXIES` so clients are not all counted as the proxy IP. |
| Rate-limited endpoints return `503` | A configured Redis limiter is unavailable. Start Redis, or use the documented memory backend for local development. Production fails closed. |

---

## Documentation

- [Architecture](docs/architecture.md) — layers, data flow, schema, design decisions
- [API reference](docs/api.md) — endpoints, payloads, status codes
- [Authentication](docs/auth.md) — sessions, CSRF, roles, endpoint protection and migrations
- [AI integration](docs/ai-integration.md) — Gnani checklist and YOLO setup

---

## Next steps

1. Add the official Gnani Evon contract and map it into the existing schema.
2. Wire the report form to `/api/v1/voice/transcribe`, `/api/v1/voice/speak` and `/api/v1/ai/analyze-image`.
3. Store uploaded media under `backend/uploads/` (or object storage) and persist URLs.
4. Add department assignment and department-management endpoints.
5. Add password reset, MFA, session administration and automatic expired-session
   cleanup.
