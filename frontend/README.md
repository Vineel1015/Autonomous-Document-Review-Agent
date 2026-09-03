# Frontend — AI Document Review Agent

React + TypeScript + Vite. The reviewer workflow: document list, upload, and
the approve/reject decision flow. See `../README.md` for the whole system.

## Dev setup

```bash
# from the repo root
docker compose up -d        # Postgres
python main.py               # backend, port 8000 — NOT `uvicorn main:app`, see root README

# from frontend/
npm install
npm run dev                  # http://localhost:5173, proxies /api/* to :8000
```

## Scripts

- `npm run dev` — Vite dev server
- `npm run build` — typecheck + production build
- `npm run typecheck` — `tsc --noEmit`
- `npm run lint` — oxlint
- `npm run api:types` — regenerates `src/api/schema.d.ts` from the backend's
  live `/openapi.json` (backend must be running on :8000). Not wired into
  every type today — `src/types/domain.ts` is hand-written and was verified
  against a generated schema once, but regenerate and diff periodically if
  the backend's models change, since nothing enforces they stay in sync
  automatically.

## Structure

- `src/api/` — `client.ts` is the single point where a future `Authorization`
  header gets added once auth exists; `documents.ts`/`reviews.ts` are typed
  fetch wrappers.
- `src/hooks/` — TanStack Query hooks. `useDocument.ts`'s status-driven
  `refetchInterval` is the crux of the whole app's UX — there's no
  websocket/SSE backend, so polling is how the UI learns a background review
  run has progressed.
- `src/lib/enums.ts` — hardcoded mirror of the backend's Pydantic enums (no
  endpoint exposes them). Update by hand if `app/models/schemas.py` changes.
- `src/routes/` — the three v1 screens, wrapped in `RootLayout` (where an
  auth guard slots in later).

## Known gaps (v1 scope, by design)

- No auth — deliberately deferred.
- Trend charts (`/companies/*`) and peer comparison (`/metrics/compare`) —
  next round, not this one.
- `react-router-dom` stays on v6 rather than the v7 that `npm audit fix`
  would pull in — two moderate CVEs there are SSR/open-redirect-specific and
  don't apply to this pure-SPA, static-route usage; revisit if that changes.
