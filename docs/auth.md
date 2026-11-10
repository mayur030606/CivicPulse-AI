# Authentication and Endpoint Authorization

Phase 3B-2 added database-backed administrator authentication. Phase 3B-3
applies those reusable dependencies to the sensitive backend endpoints while
keeping citizen reporting and public tracking available without a login.
Phase 3B-4 adds the staff SPA that consumes those endpoints with cookie and
CSRF handling, session restoration and role-aware routing. Phase 3C-2C-1 adds
configurable abuse protection for public and provider-cost endpoints without
changing the authentication or authorization contract.

## Design

- **Password hashing:** Argon2id via `argon2-cffi`.
- **Sessions:** opaque random tokens in the `civicpulse_session` HttpOnly
  cookie. The database stores only SHA-256 token hashes in `auth_sessions`.
- **CSRF:** a separate non-HttpOnly `civicpulse_csrf` cookie. Unsafe
  authenticated requests must send the same value in the `X-CSRF-Token`
  header. The server also verifies the token hash bound to the session.
- **Cookies:** `SameSite=Lax` by default. `Secure` is forced whenever
  `ENVIRONMENT=production`, even if `COOKIE_SECURE=false`.
- **Session lifetime:** absolute expiry, `SESSION_TTL_MINUTES` (default 480).
- **Brute force:** per-account failed-login count and lockout
  (`LOGIN_MAX_FAILURES=5`, `LOGIN_LOCKOUT_MINUTES=15`). Errors are always the
  generic `Invalid email or password.`
- **Abuse protection:** per-client IP sliding-window limits on login and public
  or provider-cost endpoints. The login IP limit complements, rather than
  replaces, the per-account lockout. No CAPTCHA is used.
- **Roles:** `admin`, `dispatcher`, `viewer`.

The session record stores the resolved client IP: the direct peer address, or a
forwarded address only when the direct peer is an explicitly trusted proxy.

Inactive users, expired sessions and revoked sessions are rejected with `401`.
A valid session without the required role receives `403`. A missing or invalid
CSRF token on an authenticated write also receives `403`.

No cookie-signing secret or bootstrap password is stored in source control.
Only SHA-256 hashes of high-entropy session/CSRF tokens are persisted.

## Database migrations

From `backend/`:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

- `20261108_0001_auth_foundation` creates `users`, `auth_sessions`, their
  indexes and Alembic's version table.
- `20261108_0002_status_history_actor` adds a nullable
  `status_history.changed_by_user_id` foreign key to `users` with
  `ON DELETE SET NULL`, plus an index. Existing history rows are not altered.
  The migration checks for the column first, so a database created from the
  current models by `python -m app.init_db` is also safe.

The migrations do not drop, rewrite or backfill existing incident, department,
media or status-history data.

`alembic check` still reports pre-existing legacy-schema drift (live `TIMESTAMP`
columns modelled as `DateTime`, and missing indexes on some existing foreign
keys). Those items predate Phase 3B-3 and are not part of migration
`20261108_0002`; the new actor column, index and foreign key match the model.

## First administrator

The bootstrap command reads the password interactively with `getpass`; it has
no default password and refuses to run if any administrator already exists.

```powershell
.\.venv\Scripts\python.exe -m app.cli create-admin --email admin@example.org
```

The password must be at least 12 characters. It is never accepted as a
command-line argument, printed, logged or returned by the API.

## Endpoint protection matrix

| Method | Path | Required access |
| --- | --- | --- |
| `POST` | `/api/v1/auth/login` | Public (issues session cookies; per-IP rate-limited) |
| `GET` | `/api/v1/auth/me` | Any authenticated user |
| `POST` | `/api/v1/auth/logout` | Session cookie + `X-CSRF-Token` |
| `POST` | `/api/v1/incidents` | Public citizen submission (per-IP rate-limited) |
| `GET` | `/api/v1/tracking/{tracking_id}` | Public safe-field lookup (per-IP rate-limited) |
| `GET` | `/api/v1/incidents` | `dispatcher` or `admin` |
| `GET` | `/api/v1/incidents/{incident_id}` | `dispatcher` or `admin` |
| `PATCH` | `/api/v1/incidents/{incident_id}` | `dispatcher` or `admin` + `X-CSRF-Token` |
| `GET` | `/api/v1/reports/summary` | `dispatcher` or `admin` |
| `GET` | `/api/v1/admin/overview` | `admin` only |

The legacy `/api/v1/complaints` routes were removed in Phase 3C-2A because they
targeted a `complaints` table that does not exist in the live schema. They now
return `404`; the active citizen workflow is `/api/v1/incidents` and
`/api/v1/tracking/{tracking_id}`.

`viewer` accounts can authenticate but cannot read incident lists, read incident
details, run report summaries, update records or access admin routes in this
milestone. No department-management API routes exist in the codebase, so none
were added or exposed.

## Rate limiting and client IP

The public incident and tracking endpoints, login, and provider-cost voice/AI
endpoints use a configurable sliding-window limiter. Exceeding a limit returns
`429 Too Many Requests` with an integer `Retry-After` header and
`Cache-Control: no-store`. Limits and windows are configured with the
`RATE_LIMIT_*` variables documented in `.env.example`.

Client identity is the direct peer address. `X-Forwarded-For` and `X-Real-IP`
are ignored unless the direct peer is listed in `RATE_LIMIT_TRUSTED_PROXIES`.
For a trusted proxy, the forwarded chain is walked from right to left and
trusted hops are skipped, so a client cannot spoof the header to bypass a limit.
Leave the list empty when the app is not behind a reverse proxy.

`RATE_LIMIT_BACKEND=memory` is the default and is process-local: it is suitable
for development or a single worker, but not for multiple worker processes.
Multi-worker deployments should install `backend/requirements-redis.txt` and set
`RATE_LIMIT_BACKEND=redis` with `RATE_LIMIT_REDIS_URL`. If the configured shared
backend is unavailable, protected endpoints fail closed with a generic `503`;
production startup fails when Redis is configured but unreachable. In
development, an unreachable Redis falls back to the in-memory backend with a
warning. Rate-limit keys are hashed and raw client IPs are not logged.

## Status workflow

`incidents.status` remains a plain database string for compatibility with
existing rows. API writes are constrained to this allow-list:

- `Submitted`
- `In Progress`
- `Resolved`
- `Closed`

Public `POST /incidents` accepts only the default `Submitted` state. Incident
`PATCH` rejects unknown status strings, explicit `null` status and unknown JSON
fields with `422`. Every real status change appends a `status_history` row
recording the old status, new status and authenticated `changed_by_user_id`.
Existing history rows and incident fields are never deleted or rewritten by the
update path.

## Client contract

The Phase 3B-4 staff SPA implements these rules in
`frontend/src/api/client.js` and `frontend/src/context/AuthContext.jsx`:

1. Call login with `withCredentials: true`.
2. Read the non-HttpOnly `civicpulse_csrf` cookie.
3. Send its value in `X-CSRF-Token` on `POST`, `PUT`, `PATCH` and `DELETE`
   requests to authenticated endpoints.
4. Treat `401` as "log in again" and `403` as "not permitted or CSRF failed".

Login posts normalized credentials and restores the session from `GET
/auth/me`. Logout sends the CSRF header before clearing the in-memory session.
A `401` from any protected request clears the client session and lets the
route guards redirect to `/login`; `/auth/login` and `/auth/me` are excluded
from that global event.

The public citizen pages (`/report` and `/tracking`) remain cookie-free.
The `/complaints` and `/map` SPA routes preserve their URLs but load protected
incident data only for dispatcher and admin sessions. The `/complaints` page is
a staff directory backed by `/api/v1/incidents`; it is unrelated to the removed
legacy complaints API.

## Phase 3B-4 staff interface

| Role | UI access |
| --- | --- |
| `admin` | `/dashboard` with administrator overview and report summary; `/incidents` list and detail; canonical status updates |
| `dispatcher` | `/dashboard` with report summary; `/incidents` list and detail; canonical status updates |
| `viewer` | `/dashboard` account details only; protected incident, map, report and admin data stay hidden and return `403` if requested directly |

The route guards are UX only. The backend repeats every authentication, role
and CSRF check on each request.

## Remaining gaps

- No department assignment workflow or department-management endpoints.
- No password reset, MFA, session listing or self-service account management.
- No idle timeout; sessions expire only at their absolute `expires_at`.
- Expired/revoked session rows are not automatically purged.
- The default rate-limit backend is process-local. Multi-worker deployments must
  configure Redis; an in-memory limiter is not shared across workers.
- Redis is an optional dependency and is not installed by `requirements.txt`;
  install `requirements-redis.txt` when enabling it.
- The legacy `/api/v1/complaints` API and its `Complaint` model were removed in
  Phase 3C-2A. The live citizen workflow uses `/api/v1/incidents` and
  `/api/v1/tracking/{tracking_id}`, and the live database has no `complaints`
  table.
