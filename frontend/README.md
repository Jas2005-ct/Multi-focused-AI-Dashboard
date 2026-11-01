# AI Dashboard — Frontend

React + TypeScript + Vite client for the AI Dashboard backend.

## Setup

```bash
npm ci
cp .env.example .env      # then set VITE_API_URL
npm run dev               # http://localhost:5173
```

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_URL` | `http://localhost:5000` | Backend base URL (no trailing slash) |

## Commands

| Command | Purpose |
|---|---|
| `npm run dev` | Vite dev server with HMR |
| `npm run build` | Type-check (`tsc -b`) + production build to `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run lint` | ESLint (TypeScript) |

## Structure

```
src/
├── config.ts           # API_URL + Google OAuth URL (single source of truth)
├── api/
│   ├── client.ts       # axios instance: Bearer injection, X-Request-ID,
│   │                   #   single-flight refresh on TOKEN_EXPIRED, 401 → logout
│   ├── authapi.ts      # auth pair storage (saveAuth / clearAuth / refreshSession)
│   └── dashboardapi.ts # typed calls to /api/v1 (connections, ai/query)
├── pages/              # login, register, forgotpassword, dashboard
├── components/         # SQLQueryOptimizer, DBConnectionForm, SavedConnections,
│   │                   #   ErrorModal, ApiStatus
├── routes/             # protectedroutes.tsx (auth guard)
└── types/              # auth.ts, connection.ts
```

## Auth model

- Tokens live in `localStorage`: `token` (access, 15 min), `refreshToken` (rotating, 7 days), `user`.
- On `401` with `code: "TOKEN_EXPIRED"`, `api/client.ts` refreshes **once** (single-flight, so
  concurrent requests share one rotation) and replays the original request.
- If rotation fails, credentials are cleared and the user is redirected to `/`.

## API base

All API calls target the versioned surface (`/api/v1`). The legacy `/api/*` endpoints still
exist on the backend but are deprecated — do not use them from new code.

See [`../API_REFERENCE.md`](../API_REFERENCE.md) for the full endpoint contract.
