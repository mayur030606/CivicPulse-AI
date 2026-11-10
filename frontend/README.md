# CivicPulse AI — Frontend

React 19 + Vite + Tailwind CSS v4.

Setup and run instructions live in the root [README](../README.md).

```powershell
npm install
npm run dev      # http://localhost:5173
npm test         # Node test runner
npm run build    # production build
npm run lint     # oxlint
```

Environment variables are read from the repository-root `.env` (see
`vite.config.js` → `envDir`). Only `VITE_*` variables are exposed to the browser.

Key folders:

- `src/api` — Axios client (credentials + CSRF) and endpoint wrappers
- `src/components` — layout, auth guards, UI primitives, map and complaint components
- `src/context` — session restoration, login/logout and auth state
- `src/pages` — route-level screens, including staff login, dashboard and incident management
- `src/lib` — constants, formatters, route access and view-model helpers
- `tests` — Node tests for API helpers, auth logic, route guards and view models
