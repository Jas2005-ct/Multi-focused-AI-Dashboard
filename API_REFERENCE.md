# AI Dashboard — Backend API Reference

**Base URL:** `http://localhost:5000` (or `VITE_API_URL` / `API_URL` in the frontend)

**Versioned surface:** `/api/v1` — **use this.** The legacy `/api/*` surface still works but is
deprecated and answers with `Deprecation: true` + `Link: …; rel="successor-version"`.

**Interactive docs:** `/openapi/swagger` (Swagger UI) · `/openapi.json` (OpenAPI 3.0 spec)

**CORS:** `http://localhost:5173`, `http://127.0.0.1:5173`

---

## 1. Conventions

### 1.1 Authentication

Every `/api/*` and `/auth/*` endpoint except `GET /auth/login`, `GET /auth/callback`,
`GET /health`, `GET /ready` and `GET /openapi.json` requires a **Bearer access token**:

```
Authorization: Bearer <access_token>
```

There is **no session cookie fallback**. An unauthenticated request to a protected API route
answers `401` with a JSON body (never a redirect).

### 1.2 Token model

| Token | TTL | Storage | Notes |
|---|---|---|---|
| Access | 15 min | `localStorage.token` | Sent as `Authorization: Bearer …` |
| Refresh | 7 days | `localStorage.refreshToken` | Rotating: single use, replaced on every refresh |

Both are signed HS256 JWTs with a `typ` claim (`access` / `refresh`) so a token can never be
used for the wrong purpose.

### 1.3 Error envelope

Every error response uses the same shape:

```json
{
  "success": false,
  "error": "Connection not found",
  "message": "No connection with id 26 belongs to this user.",
  "request_id": "0f3c1a2b-…"
}
```

`request_id` is echoed in the `X-Request-ID` response header and is also the first field to
quote when reporting a problem.

### 1.4 Error codes on 401

`require_auth` returns a machine-readable `code` so the client can decide whether to retry:

| `code` | Meaning | Client action |
|---|---|---|
| `MISSING_TOKEN` | No `Authorization: Bearer` header | Send the user to login |
| `TOKEN_EXPIRED` | Access token expired | Rotate once via `POST /auth/refresh`, then replay |
| `INVALID_TOKEN` | Malformed / wrong `typ` / revoked | Clear credentials, send to login |

The frontend implements this as a **single-flight** refresh: concurrent `TOKEN_EXPIRED`
responses share one rotation, so a burst of parallel requests cannot burn the refresh family.

---

## 2. System

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | no | Liveness + database connectivity |
| GET | `/ready` | no | Readiness probe for load balancers |
| GET | `/openapi.json` | no | OpenAPI 3.0 specification |
| GET | `/api/v1/health` | no | Same as `/health`, versioned alias |
| GET | `/api/v1/ready` | no | Same as `/ready`, versioned alias |

```jsonc
// GET /health
{ "status": "ok", "database": "connected" }        // 200
{ "status": "error", "database": "error" }          // 503
```

---

## 3. Auth — `/auth`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/auth/login` | no | Start Google OAuth (redirect) — **503 when OAuth is disabled** |
| GET | `/auth/callback` | no | OAuth callback → redirects to `/dashboard?token=…&refreshToken=…&user=…` |
| POST | `/auth/login` | no | Email + password login |
| POST | `/auth/register` | no | Create account |
| POST | `/auth/logout` | no | Clear the browser session (no-op for JWT clients) |
| POST | `/auth/refresh` | no | Rotate the refresh token → new pair |
| GET | `/auth/me` | yes | Current user profile |
| POST | `/auth/forgot-password` | no | Request a password-reset OTP |
| POST | `/auth/resend-otp` | no | Resend the OTP (same silent-cooldown behaviour) |
| POST | `/auth/verify-otp` | no | Verify the OTP without consuming it |
| POST | `/auth/reset-password` | no | Consume the OTP and set a new password |

### 3.1 `POST /auth/login` · `POST /auth/register`

Request:

```json
{ "email": "user@example.com", "password": "Str0ngPass!2345", "name": "User" }
```

Password rules: >= 8 chars, one uppercase, one lowercase, one digit. A password
that fails the policy answers `422` with a readable reason and **never** echoes
the submitted value back:

```json
{
  "success": false,
  "error": "Validation failed",
  "message": "Password must contain at least one uppercase letter",
  "details": [ { "type": "value_error", "loc": ["password"], "msg": "Password must contain at least one uppercase letter" } ]
}
```

Response `201` (register) / `200` (login):

```json
{
  "token": "<access jwt>",
  "refreshToken": "<refresh jwt>",
  "user": { "id": 1, "email": "user@example.com", "name": "User" }
}
```

Errors: `400` invalid input, `401` bad credentials, `409` email already registered.

### 3.2 `POST /auth/refresh`

```json
{ "refreshToken": "<refresh jwt>" }
```

→ `200` with a **new** `{ token, refreshToken, user }` pair. The presented token is revoked
immediately. Replaying a consumed refresh token is treated as theft: the **entire token family
for that user is revoked** and the call answers `401`.

### 3.3 `GET /auth/me`

→ `200 { "id": 1, "email": "user@example.com", "name": "User" }`

### 3.5 Google OAuth (disabled by default)

Google sign-in is **off** unless `ENABLE_GOOGLE_OAUTH=true` is set on the backend
(plus `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`). The frontend hides the
"Continue with Google" button unless `VITE_ENABLE_GOOGLE_OAUTH=true` is set.

While disabled, `GET /auth/login` and `GET /auth/callback` answer `503`:

```json
{
  "success": false,
  "error": "Google sign-in is disabled",
  "message": "Google OAuth is currently disabled. Please sign in with your email and password."
}
```

To re-enable it, set these on the backend and restart:

```bash
ENABLE_GOOGLE_OAUTH=true
GOOGLE_CLIENT_ID=…
GOOGLE_CLIENT_SECRET=…
```

and on the frontend:

```bash
VITE_ENABLE_GOOGLE_OAUTH=true
```

### 3.6 OTP flow

`POST /auth/forgot-password` and `POST /auth/resend-otp` **always answer `200` with the same
message**, whether or not the address exists — this prevents account enumeration. Requests
inside the 60-second cooldown are silently dropped (still `200`, no `429`), so an observer
cannot distinguish a known address from a recently-mailed one.

`POST /auth/verify-otp` → `200` on success, `400` invalid OTP, `429` too many attempts.
`POST /auth/reset-password` → `200` on success, `400` invalid OTP / weak password.

---

## 4. AI — `/api/v1/ai/query`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/ai/query` | yes | SQL generation or natural-language data answer |

```json
{
  "query": "how many projects do I have?",
  "connection_id": 26,
  "mode": "auto"
}
```

| `mode` | Behaviour |
|---|---|
| `auto` (default) | LangGraph ReAct agent — the model picks the tools to call |
| `sql` | LCEL chain — direct single-query generation |
| `answer` | Agent restricted to data answers |

Success response:

```json
{
  "success": true,
  "message": "ok",
  "data": {
    "type": "answer",
    "answer": "There are 3 projects.",
    "tables": ["portfolio_project"],
    "count": 3,
    "rows": [],
    "toolCalls": [
      { "name": "count_rows", "args": { "user_id": 1, "db_id": 26, "table_name": "portfolio_project" }, "result": 3 }
    ]
  },
  "request_id": "…"
}
```

For `type: "query"` the payload carries `sql` instead of `answer`/`rows`.

**Read-only guarantee.** All generated SQL is parsed with `sqlglot` and rejected unless it is
a single `SELECT`/`WITH` statement; write intent in the question is refused before any tool
runs. Row results are capped at 50 and `LIMIT 50` is added when missing.

Errors: `400` validation, `401` auth, `500` upstream LLM / target-DB failure.

---

## 5. Database connections — `/api/v1/connections`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/connections` | yes | Create a connection (credentials encrypted) |
| GET | `/api/v1/connections` | yes | List connections (paginated) |
| GET | `/api/v1/connections/{db_id}` | yes | One connection + its table list |
| DELETE | `/api/v1/connections/{db_id}` | yes | Delete a connection and release its pool |
| POST | `/api/v1/connections/{db_id}/test` | yes | Test reachability + credentials |
| GET | `/api/v1/connections/{db_id}/tables` | yes | Table names |
| GET | `/api/v1/connections/{db_id}/tables/{table_name}` | yes | Column metadata for one table |

### 5.1 `POST /api/v1/connections`

```json
{
  "name": "Production DB",
  "host": "db.example.com",
  "port": 5432,
  "database": "app",
  "username": "app_user",
  "password": "••••••••",
  "db_type": "postgresql",
  "sslmode": "require"
}
```

`db_type` ∈ `postgresql` | `mysql`. `sslmode` ∈ `require` | `verify-ca` | `verify-full` |
`allow` | `disable`. `connection_string` may be supplied instead of the discrete fields.

Secrets are stored encrypted (versioned Fernet) and **never** returned by any endpoint.

### 5.2 `GET /api/v1/connections?page=1&per_page=20`

```json
{
  "success": true,
  "message": "ok",
  "data": {
    "page": 1, "per_page": 20, "total": 2, "pages": 1,
    "connections": [
      { "id": 26, "name": "Production DB", "host": "db.example.com", "port": 5432,
        "database": "app", "username": "app_user", "db_type": "postgresql",
        "sslmode": "require", "created_at": "2026-10-10T12:00:00", "last_used": null }
    ]
  },
  "request_id": "…"
}
```

### 5.3 `POST /api/v1/connections/{db_id}/test`

→ `200` with `{ "success": true, "message": "Connection successful" }` when the target
database answers `SELECT 1`. A failed connection also answers `200`, with
`success: false` and the underlying driver message in `message` (e.g. *"Connection failed:
could not translate host name …"*) so the UI can show something actionable.

### 5.4 Ownership

Every connection endpoint is scoped to the authenticated user. A row belonging to another
user is reported as `404` (not `403`) so ids cannot be probed.

---

## 6. Legacy surface — `/api/*` (deprecated)

| Method | Path | Superseded by |
|---|---|---|
| GET | `/api/` | — (greeting) |
| POST | `/api/sql-query/` | `POST /api/v1/ai/query` |
| POST | `/api/ai/query` | `POST /api/v1/ai/query` |
| POST | `/api/db-connection` | `POST /api/v1/connections` |
| POST | `/api/test-connection/` | `POST /api/v1/connections/{id}/test` |
| DELETE | `/api/delete-connection` | `DELETE /api/v1/connections/{id}` |
| GET | `/api/get-connections/` | `GET /api/v1/connections` |

These still work, but they return the **old flat response shapes** (no `data` envelope) and
carry `Deprecation: true`. New integrations must use `/api/v1`.

---

## 7. Rate limits

`flask-limiter` is active in production (disabled when `FLASK_ENV=testing`). Limits are
configured in `backend/config.py`; the storage backend is in-memory by default and should be
pointed at Redis for multi-worker deployments.

---

## 8. Quick reference (curl)

```bash
# Register
curl -X POST http://localhost:5000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com","password":"Str0ngPass!2345","name":"User"}'

# Use the access token
TOKEN=<access_token from register>
curl http://localhost:5000/api/v1/connections -H "Authorization: Bearer $TOKEN"

# Ask a question
curl -X POST http://localhost:5000/api/v1/ai/query \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"query":"what tables exist?","connection_id":26,"mode":"auto"}'
```

---

## 9. Related documents

- [`docs/CODEBASE_ANALYSIS.md`](docs/CODEBASE_ANALYSIS.md) — structure, folder map, known debt
- [`docs/runbook.md`](docs/runbook.md) — deployment, key rotation, troubleshooting
- [`docs/plan.md`](docs/plan.md) — the completed 8-phase revamp plan
