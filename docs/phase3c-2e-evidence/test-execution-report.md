# CivicPulse AI — Phase 3C-2E Real-Browser E2E Verification

**Date:** 2026-11-09 (run window 14:43:09–14:43:39 UTC)
**Project root:** `D:\CivicPulse-AI`
**Frontend:** `http://127.0.0.1:5173` (Vite 8.3.6, React 19, development mode)
**Backend:** `http://127.0.0.1:8080` (FastAPI, `ENVIRONMENT=development`)
**Database:** local MySQL 8.0.46, database `civicpulse`, Alembic `20261108_0002`
**Browser:** Microsoft Edge 157.0.4341.42, headless, driven by Playwright 1.65.0 (`channel: msedge`)
**Node:** v25.9.0

## Result at a glance

| Item | Result |
| --- | --- |
| Requested scenarios 1–14 | **14 / 14 executed** |
| Scenario records (includes sub-scenario 3b) | **15 / 15 PASS** |
| Real browser used | **Yes** — Edge, real FastAPI backend, real MySQL data |
| Requested scenario skipped | **No** |
| Uncaught browser page errors | **0** |
| Unexpected non-network console errors | **0** |
| Unexpected HTTP error responses | **0** of 42 observed |
| Real failed network requests | **0** (2 benign navigation aborts) |
| Incidents before / after | **6 / 6** |
| Status-history rows before / after | **0 / 0** |
| Test incident status before / after | `Submitted` / `Submitted` |
| Temporary accounts / sessions after cleanup | **0 / 0** |

All 14 requested scenarios were exercised in a real browser. This is **not** a claim of full end-to-end coverage of every application workflow: successful incident creation, successful status updates, live Gnani AI calls, and map tile rendering were intentionally not performed (see “Tests not performed”).

## Safety and data-integrity controls

- `backend/.env` was never opened or printed.
- No password, cookie value, session ID, CSRF token, API key, or credential was written to evidence or logs.
- Three synthetic temporary accounts (admin, dispatcher, viewer) were created through `auth_service.create_user` with random passwords held only in the external test process. They were deleted after the run.
- No existing incident was modified. The only write attempted against an incident was the viewer `PATCH` in scenario 9, which the backend rejected with `403`; the record was verified unchanged.
- No live Gnani API was called.
- No security control was weakened or bypassed.

## Evidence index

All paths are under `docs/phase3c-2e-evidence/`.

| File | Contents |
| --- | --- |
| `results.json` | Full scenario/check record, browser metadata, console/network events |
| `http-status-results.json` | Navigation statuses, explicit API checks, observed error responses |
| `console-error-summary.json` | Console/page/network error classification |
| `viewport-sizes.json` | Desktop and mobile viewport sizes tested |
| `screenshots/` | 29 browser screenshots |

## Browser tests actually executed

These were real UI interactions in Edge: navigation, form fills, button clicks, reloads, viewport changes, and screenshots.

| # | Scenario | Result | What was verified | Evidence |
| --- | --- | --- | --- | --- |
| 1 | Anonymous home | PASS | `/` rendered; staff sign-in and report entry points visible | `01-anonymous-home-desktop.png` |
| 2 | Anonymous protected dashboard | PASS | Direct `/dashboard` redirected client-side to `/login`; login form rendered | `02-anonymous-dashboard-redirect-login.png` |
| 3 | Anonymous protected incidents | PASS | Direct `/incidents` and `/incidents/1` redirected to `/login` | `03-anonymous-incidents-redirect-login.png` |
| 3b | Login redirect preservation | PASS | Anonymous `/incidents` → login → admin landed on `/incidents`, not `/dashboard` | `04-login-redirect-preserved-incidents.png` |
| 4 | Admin login + dashboard | PASS | UI login succeeded; “City operations dashboard”, “Administrator overview”, and “Incident reports” rendered; admin nav exposed Incidents | `05-login-desktop.png`, `06-admin-dashboard-desktop.png` |
| 5 | Admin staff functionality | PASS | Incident list returned 6 records; detail for incident #7 rendered; status control present but **not used** | `07-admin-incidents-desktop.png`, `08-admin-incident-detail-desktop.png` |
| 6 | Dispatcher access | PASS | UI login; “Dispatch dashboard” and report summary rendered; incident list loaded | `09-dispatcher-dashboard-desktop.png`, `10-dispatcher-incidents-desktop.png` |
| 7 | Dispatcher denied admin-only | PASS | No “Administrator overview” in UI; in-browser `GET /api/v1/admin/overview` returned `403` | `11-dispatcher-no-admin-overview.png` |
| 8 | Viewer read-only access | PASS | “Staff account” and “Read-only viewer account” rendered; no admin overview, no report summary, no Incidents nav; `/incidents` and `/incidents/7` showed the client-side `403` screen; backend denied incident list/admin overview with `403` | `12-viewer-dashboard-desktop.png`, `13-viewer-incidents-403.png`, `14-viewer-incident-detail-403.png` |
| 9 | Viewer status update rejected | PASS | Viewer `PATCH /api/v1/incidents/7` with the viewer’s real session and a valid CSRF token returned `403`; incident status remained `Submitted` | `15-viewer-update-rejected-403.png` |
| 10 | Logout + session expiration | PASS | UI logout → `/login`; post-logout `/dashboard` → `/login`; server-side revocation of the temp session followed by a UI Refresh produced `401` and the “Your session expired” notice | `16-session-expired-login.png` |
| 11 | Refresh restores valid session | PASS | Reloading `/incidents` with a valid dispatcher session kept the user authenticated and reloaded the list | `17-refresh-session-restored.png` |
| 12 | Login, dashboard, incident list, tracking | PASS | Tracking page idle state, empty-ID validation, unknown-ID `404` state; public report page rendered | `18-tracking-idle-desktop.png`, `19-tracking-not-found-desktop.png`, `20-report-page-desktop.png` |
| 13 | Responsive desktop + mobile | PASS | 1440×900 and 390×844; home, login, tracking at both sizes; admin dashboard/incidents and viewer dashboard at mobile; no horizontal overflow; mobile nav visible | `21-home-{desktop,mobile}.png`, `22-login-{desktop,mobile}.png`, `23-tracking-{desktop,mobile}.png`, `24-admin-dashboard-mobile.png`, `25-admin-incidents-mobile.png`, `26-viewer-dashboard-mobile.png` |
| 14 | Console + network errors | PASS | 0 page errors; 0 non-network console errors; 0 unexpected HTTP errors; 0 real request failures | `console-error-summary.json`, `http-status-results.json` |

### Important nuance for scenario 9

The viewer UI never renders a status-update form because the `/incidents/:id` route guard blocks viewers with a `403` screen. The rejection was therefore verified with an in-browser `PATCH` using the viewer’s real session and CSRF token. This exercises the real backend authorization path without inventing a UI control that does not exist.

### Important nuance for scenario 10

The configured session TTL is 480 minutes, so true time-based expiry was not waited for. Expiry was simulated by revoking **only the temporary test session** server-side, then triggering a UI request. No incident data was touched.

## API checks

These checks were executed from inside the browser using the authenticated session cookies (same-origin `fetch`), not from a separate API test client.

| Role | Method | Path | Status | Expected | Result |
| --- | --- | --- | --- | --- | --- |
| admin | GET | `/api/v1/auth/me` | 200 | 200 | PASS |
| admin | GET | `/api/v1/admin/overview` | 200 | 200 | PASS |
| admin | GET | `/api/v1/reports/summary` | 200 | 200 | PASS |
| admin | GET | `/api/v1/incidents` | 200 | 200 | PASS |
| admin | GET | `/api/v1/incidents/7` | 200 | 200 | PASS |
| dispatcher | GET | `/api/v1/incidents` | 200 | 200 | PASS |
| dispatcher | GET | `/api/v1/admin/overview` | 403 | 403 | PASS |
| viewer | GET | `/api/v1/auth/me` | 200 | 200 | PASS |
| viewer | GET | `/api/v1/incidents` | 403 | 403 | PASS |
| viewer | GET | `/api/v1/admin/overview` | 403 | 403 | PASS |
| viewer | PATCH | `/api/v1/incidents/7` | 403 | 403 | PASS |

Observed error responses across the run (all expected):

| Classification | Count |
| --- | --- |
| Anonymous `/auth/me` probe `401` | 36 |
| Admin-only overview `403` for non-admin | 2 |
| Viewer incident list `403` | 1 |
| Viewer incident update `403` | 1 |
| Expired-session report summary `401` | 1 |
| Unknown tracking ID `404` | 1 |
| **Unexpected** | **0** |

### SPA navigation note

Protected-route document requests return HTTP `200` because Vite serves the SPA shell. The redirect to `/login` and the `403` access-denied screens are performed client-side by the React route guards. The backend independently enforced `401`/`403` on the API calls, which is what the table above records.

## Browser console and network summary

From `console-error-summary.json`:

| Metric | Count |
| --- | --- |
| Console entries of type `error` | 42 |
| — network status messages for expected `4xx` | 42 |
| — non-network console errors | 0 |
| Uncaught page errors | 0 |
| Request failures | 2 |
| — benign aborts caused by navigation | 2 |
| — real request failures | 0 |
| Observed HTTP error responses | 42 |
| Unexpected HTTP error responses | 0 |

The two aborted requests were `GET /favicon.svg` and a duplicate `GET /api/v1/reports/summary` in the dispatcher context. Both were in-flight requests cancelled by navigation/reload. React `StrictMode` is enabled in development, which intentionally double-invokes effects and produces duplicate requests; one duplicate can be aborted when the page navigates. No server error or failed application action resulted.

## Viewport sizes tested

| Name | Size |
| --- | --- |
| Desktop | 1440 × 900 |
| Mobile | 390 × 844 |

Pages checked at both sizes: home, login, tracking. Mobile-only checks: admin dashboard, admin incident list, viewer dashboard. All tested pages had `scrollWidth <= innerWidth` (no horizontal overflow).

## Automated unit tests (separate from browser E2E)

| Suite | Command | Result |
| --- | --- | --- |
| Backend | `python -m unittest discover -s tests -v` | **115 tests, OK** (10.29 s) |
| Frontend | `npm test` | **126 pass, 0 fail** (1.11 s) |
| Frontend lint | `npm run lint` | **exit 0**, 7 warnings, 0 errors |
| Frontend build | `npm run build` | **exit 0**, chunk-size warning only |

Lint warnings: 2 × `react(only-export-components)` in `AuthContext.jsx`; 5 × `react(set-state-in-effect)` across `DashboardPage.jsx`, `IncidentDetailPage.jsx`, and `IncidentsPage.jsx`. These are pre-existing warnings, not introduced by this verification.

## Mocked / isolated tests

- The backend unit suite uses an isolated in-memory SQLite database and mocked or stubbed external integrations (Gnani, YOLO, rate-limit clock, upload handling). It does **not** touch the live MySQL database.
- The frontend unit suite is pure logic testing with Node’s test runner; it does not launch a browser.
- The browser E2E suite above was **not mocked**: it used the real FastAPI process, the real MySQL database, real cookies, and real CSRF validation.
- No live Gnani provider call was made or mocked in the browser suite.

## Tests not performed

The following were intentionally not performed, so this report does not claim full application E2E coverage:

- Successful incident creation (`POST /api/v1/incidents`) and successful dispatcher/admin status update (`PATCH` returning `200`) — skipped to avoid modifying existing incident data.
- Live Gnani Prisma speech-to-text, Timbre text-to-speech, or Evon NLU calls.
- Voice recording/transcription UI, image upload/YOLO analysis, and AI classification workflows.
- Map page and Leaflet/OpenStreetMap tile rendering.
- Real 480-minute session expiry wait (simulated via server-side revocation instead).
- Firefox, Safari/WebKit, or other non-Chromium browsers.
- Accessibility audit, performance profiling, and visual-regression comparison.
- Production-mode `Secure` cookie behavior in a browser (covered only by the prior milestone’s API-level check).
- 404 page, complaints page, and map page navigation.
- Mobile touch gestures beyond layout/overflow checks.

## Cleanup and final state

| Item | Result |
| --- | --- |
| Temporary users created | 3 (admin, dispatcher, viewer) |
| Temporary users deleted | 3 |
| Sessions deleted | 12 |
| Credentials file | Removed |
| Final users | 0 |
| Final sessions | 0 |
| Final incidents | 6 (unchanged) |
| Final status-history rows | 0 (unchanged) |
| Backend/frontend processes | Stopped |
| Application source files changed | None |

Screenshots contain only synthetic test-account identifiers (for example `e2e.phase3c2e.*@example.test`); the accounts have been deleted. No passwords, session values, CSRF tokens, or API keys appear in any evidence file.
