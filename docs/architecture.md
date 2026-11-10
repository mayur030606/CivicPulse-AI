# Architecture

## Overview

CivicPulse AI is split into three deployable pieces:

```text
┌─────────────────────────────┐
│  React + Vite + Tailwind    │
│  pages / components / api   │
└──────────────┬──────────────┘
               │  HTTP (JSON, multipart)
               ▼
┌─────────────────────────────┐
│  FastAPI                    │
│  routes → services → models │
│         ↘ schemas           │
└───────┬─────────────┬───────┘
        │             │
        ▼             ▼
┌──────────────┐  ┌──────────────────────────────┐
│  MySQL       │  │  AI integrations             │
│  SQLAlchemy  │  │  Prisma / Timbre / Evon      │
└──────────────┘  │  YOLO (Ultralytics)          │
                  └──────────────────────────────┘
```

The frontend never calls Gnani or YOLO directly. All credentials stay on the
backend, and the backend is the only component that talks to MySQL.

## Request flow

### Create an incident

1. The user submits the form on `/report`.
2. `src/api/incidents.js` posts JSON to `/api/v1/incidents`.
3. Vite proxies `/api` to FastAPI on port 8080 in development.
4. `app/core/rate_limit.py` checks the client against the incident-creation
   policy and returns `429` with `Retry-After` when the limit is exceeded.
5. `routes/incidents.py` validates the body with `schemas/incident.py`.
6. `services/incidents.py` generates a tracking ID and persists the row.
7. FastAPI serialises the ORM object through `IncidentRead`.

Citizens can then look up the public-safe status at
`GET /api/v1/tracking/{tracking_id}`.

> The legacy `/api/v1/complaints` flow shown in older revisions was removed in
> Phase 3C-2A because it targeted a `complaints` table absent from the live
> database. Incidents are the only active citizen reporting workflow.

### AI-assisted intake (target design)

```text
audio ──► Prisma (STT) ──┐
photo ──► YOLO ──────────┼──► Evon (NLU) ──► structured incident ──► MySQL
text ────────────────────┘                          │
                                                    └──► Timbre (TTS) ──► citizen
```

Each step is optional and independent. Prisma STT and Timbre TTS are implemented;
Evon NLU and YOLO still return `501`/`503` instead of pretending the AI call
succeeded.

## Backend layers

| Folder | Responsibility |
| --- | --- |
| `app/core` | Settings, auth dependencies, trusted-proxy resolution and rate limiting |
| `app/database.py` | Engine, session factory, `Base`, `get_db` dependency, connection check |
| `app/models` | SQLAlchemy tables and enums |
| `app/schemas` | Pydantic request/response contracts and validation |
| `app/routes` | HTTP layer: paths, status codes, dependency wiring |
| `app/services` | Business logic and external integrations |

Rules of thumb:

- Routes do not contain SQL or third-party API calls.
- Services do not raise `HTTPException`; the app maps domain errors globally.
- Schemas are the public contract; ORM models are internal.
- `app/main.py` owns CORS, lifespan and error handlers.

## Rate limiting and abuse protection

Public incident submission, tracking lookup, login, and provider-cost voice/AI
endpoints use per-client sliding-window limits. A route opts in with a FastAPI
dependency, so staff list/detail/update/report/admin routes are unchanged.

- **Client identity.** `app/core/network.py` uses the direct peer address unless
  that peer is in `RATE_LIMIT_TRUSTED_PROXIES`. Only then are `X-Forwarded-For`
  and `X-Real-IP` considered. Forwarded chains are walked from right to left,
  skipping trusted proxies, so an untrusted client cannot spoof the header.
- **Backends.** `memory` is the default and is process-local; it is documented
  for development and single-worker use only. `redis` is optional via
  `backend/requirements-redis.txt` and uses an atomic sorted-set Lua script so
  multiple workers share one limit.
- **Failure behavior.** A configured backend failure returns a generic `503`
  rather than silently allowing traffic. Production startup fails if Redis is
  configured but unreachable; development falls back to the memory backend with
  a warning. The app never claims the in-memory backend is multi-worker safe.
- **Privacy.** Limiter keys hash the client identifier with SHA-256; raw IP
  addresses are not logged.

## Database schema

### `incidents`

The active citizen reporting table. Column types and nullability mirror the
live MySQL schema.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | int PK | Auto-increment |
| `tracking_id` | varchar(50) | Unique public identifier (`CP-YYYYMMDD-XXXXXX`) |
| `category` | varchar(100) | Required |
| `description` | text | Optional, original language |
| `severity` | varchar(30) | low / medium / high / critical |
| `priority` | varchar(30) | low / medium / high / critical |
| `status` | varchar(30) | Submitted / In Progress / Resolved / Closed |
| `latitude`, `longitude` | decimal(10,7) | Nullable |
| `created_at` | datetime | Server-managed |

### Related tables

| Table | Purpose |
| --- | --- |
| `citizen_reports` | Optional citizen transcript/language rows linked to an incident |
| `incident_images` | Optional media path and detection result linked to an incident |
| `status_history` | Audit rows appended by incident status updates |
| `departments` | Department reference data |
| `users`, `auth_sessions` | Staff authentication, managed by Alembic |

Workflow enums are defined once in `app/models/enums.py` and reused by Pydantic
schemas. The live `incidents.status` column is a plain `VARCHAR`; API writes are
constrained to the `IncidentStatus` allow-list.

> There is no `complaints` table. The legacy model, schema, service and routes
> were removed in Phase 3C-2A.

## Frontend structure

| Folder | Responsibility |
| --- | --- |
| `src/pages` | Route-level screens, data fetching per page |
| `src/components/layout` | Navbar, footer, shell |
| `src/components/ui` | Reusable presentational primitives |
| `src/components/complaints` | Incident card composition (legacy folder name) |
| `src/components/map` | Leaflet wrapper |
| `src/api` | Axios instance (credentials + CSRF) and endpoint helpers |
| `src/context` | Auth provider, session restoration, login/logout state |
| `src/components/auth` | Route guards, loading, sign-in-required and 403 states |
| `src/lib` | Constants, formatters, route access and view-model helpers |

The Axios base URL is `/api/v1` by default. Vite's `envDir` points at the
repository root so `frontend` and `backend` share one `.env`. Phase 3B-4 adds
the staff SPA on top of the protected Phase 3B-3 endpoints; the backend remains
the authorization boundary.

## Design decisions

1. **No invented AI contracts.** Implemented Gnani services use the official
   published contracts; the remaining Evon stub fails loudly with `501` rather
   than silently returning fake data.
2. **Shared `.env`.** One source of truth for local development; Vite only
   exposes `VITE_*` values to the browser.
3. **Synchronous SQLAlchemy.** Simple and predictable for the scaffold. Switch
   to async sessions if AI calls make concurrency a bottleneck.
4. **Dev table creation only.** `init_db.py` is a convenience. Production schema
   changes use Alembic; the current head is
   `20261108_0002_status_history_actor` (nullable incident audit actor).
5. **Lazy YOLO loading.** Keeps startup fast and the core install small; the
   model is loaded on the first image request.
6. **Media references, not blobs.** `incident_images.image_path` and
   `citizen_reports.transcript` keep rows small and allow local disk or object
   storage later.
7. **`tracking_id`.** Citizens get a stable, non-sequential identifier;
   internal joins still use integer IDs. It is always generated server-side;
   client-supplied values are rejected.
8. **Pluggable rate limiting.** A small dependency-based limiter avoids adding a
   mandatory Redis dependency. The memory backend keeps local development simple,
   while the optional Redis backend is the documented multi-worker path.

## Extension points

- **Auth:** Phase 3B-2 adds Argon2id passwords, opaque server-side sessions,
  HttpOnly cookies, CSRF protection and reusable role dependencies in
  `app/core/security.py` and `app/core/dependencies.py`. Phase 3B-3 applies
  those dependencies to incident reads/updates, report summaries and admin
  overview. Phase 3C-2A removes the broken legacy complaints API. Phase 3B-4
  adds the staff SPA:
  login, `/auth/me` restoration, CSRF logout, role-aware routes, the
  role-specific dashboard, and dispatcher/admin incident management.
- **Abuse protection:** Phase 3C-2C-1 adds configurable per-client limits to
  public incident/tracking, login and provider-cost endpoints, with optional
  Redis for multi-worker deployments.
- **Background work:** move transcription, YOLO inference and TTS into a task
  queue once requests become long-running.
- **Analytics:** add `/api/v1/analytics/*` routes backed by aggregate queries;
  the dashboard placeholders are ready for them.
- **Media storage:** replace local `uploads/` with S3-compatible storage and
  persist the resulting URLs.
- **Geocoding:** resolve free-text location hints to `latitude`/`longitude`
  server-side when a citizen does not share their location.
