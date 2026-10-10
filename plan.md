# Multi-focused-AI-Dashboard — Backend Revamp Implementation Plan

## 0. Decisions (locked)

- **Framework:** Keep Flask + `flask-openapi3` (`backend/app.py:16`). No FastAPI migration.
- **Auth storage:** Keep `localStorage` JWT (`frontend/src/api/client.ts:8`). Add short-lived access + rotating refresh tokens (both in `localStorage`), with XSS mitigation notes (CSP, short TTL).
- **AI stack:** Both LangChain LCEL (learning basics) + LangGraph ReAct (main path). Code heavily commented to explain prompt → model → tools → loop flow.
- **Scope:** Every phase works on backend + frontend simultaneously.
- **Branching:** Each phase = separate feature branch from `developments`. No next phase until previous PR is merged.
- **PR base branch:** `developments`.

> Base branch confirmed: `developments` (existing remote branch, matches `AGENT.md:4`). All phase PRs target `developments`.

## 1. Branch / PR / Commit conventions

- Branches: `feature/phase-0-baseline`, `feature/phase-1-config-security`, `feature/phase-2-auth`, `feature/phase-3-connections`, `feature/phase-4-ai-agent`, `feature/phase-5-api-contract`, `feature/phase-6-quality-deploy`, `feature/phase-7-rollout`
- PR titles: `To dev: <type>: <description>` (e.g. `To dev: feat: phase-2 auth revamp with refresh`)
- Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`
- Merge method: `squash` into `developments`, then delete feature branch.
- Each phase must be independently shippable with backwards-compatible shims until Phase 5 cutover.

## 2. PR + Review + Merge Workflow (mandatory per phase)

### 2.1 Per-phase lifecycle (repeat 8x)

1. `git checkout developments && git pull && git checkout -b feature/phase-N`
2. Implement backend + frontend together per phase spec below.
3. Self-check (must pass before PR):
   - backend: `pytest`, `ruff`, `black --check`
   - frontend: `npm run build` (`tsc -b`), `npm run lint`
   - manual smoke: register → connect → query → answer
4. Push + create PR:
   - base: `developments`, head: `feature/phase-N`
   - title: `To dev: feat: phase-N <short scope>`
   - body must include: scope, endpoints touched, breaking changes, test evidence, frontend screenshots, rollback notes.
5. Subagent review (different model from implementer):
   - Launch `reviewer` subagent on PR diff — bugs, security, performance, architecture, maintainability, no file writes.
   - Launch second pass with `architect`/`reviewer` as second model: focus on security + LangChain/LangGraph correctness (`backend/ai_dashboard/chains/agent_chain.py:176`, `backend/ai_dashboard/chains/sql_chain.py:101`, `backend/security/dec.py:6`, `backend/security/crypto.py:6`).
   - Both return: verdict `APPROVE` / `REQUEST_CHANGES` + `file:line` findings + severity P0/P1/P2.
6. Fix loop:
   - `REQUEST_CHANGES` → fix via `quick-fix` subagent or manual, push, re-run self-check, re-request review. Max 2 rounds; 3rd round = stop and escalate.
   - P0/P1 must be zero before merge. P2 may defer with linked TODO issue.
7. Merge: `squash`, message `feat: phase-N ...`. Delete feature branch. `git checkout developments && git pull`.
8. Gate: tag `phase-N-done`, then open next branch.

### 2.2 Reviewer subagent prompt (paste into Task tool)

> `subagent_type: reviewer`
> `Review PR head:feature/phase-N base:developments. Check: (1) auth/JWT/OTP flaws, (2) SQL injection / write-guard bypass, (3) Fernet key handling, (4) connection pool / thread safety, (5) LangChain bind_tools + LangGraph loop correctness, (6) REST contract breaks vs frontend/src/api/*.ts, (7) secrets in logs. Return severity-tagged findings with file:line + fix suggestion. No edits. Verdict APPROVE or REQUEST_CHANGES.`

Second reviewer (other model): same prompt + `Focus only as security auditor + LangGraph mentor; explain LangChain/LangGraph flow issues pedagogically.`

### 2.3 Merge checklist (paste into PR body)

- [ ] Base is `developments`, title matches `To dev: <type>: <desc>`
- [ ] Backend + frontend changed together, old routes shimmed or migrated
- [ ] `pytest` / `tsc` / `eslint` evidence attached
- [ ] Reviewer-1: APPROVE, Reviewer-2 (other model): APPROVE
- [ ] Zero P0/P1, P2 linked as issues
- [ ] `API_REFERENCE.md` updated if endpoints changed
- [ ] No `.env` / OTP / password in diff or logs

## 3. Global Definition of Done (every phase)

- [ ] `pytest` + `tsc -b` + `eslint` pass
- [ ] Old frontend still works (or shim documented)
- [ ] `API_REFERENCE.md` delta noted
- [ ] No secrets in logs, no OTP/password in stdout

---

## Phase 0 — Baseline & Safety Net
**Branch:** `feature/phase-0-baseline` → PR to `developments`

**Goal:** Freeze current behavior before refactor.

Backend:
- Snapshot contract tests for: `POST /auth/login`, `POST /auth/register`, `POST /api/sql-query/` (`backend/ai_dashboard/routes.py:44`), `POST /api/db-connection`, `GET /api/get-connections/`, `POST /api/test-connection/`, `DELETE /api/delete-connection`.
- Audit `backend/.env` committed → gitignore, create `.env.example` parity. Document `ENCRYPTION_KEY` vs `SECRET_KEY` gap (`backend/security/crypto.py:6`, `backend/app.py:23`).
- Add `ruff/black`, `pytest` skeleton.
- Confirm base branch `developments` is up to date with remote before branching.

Frontend:
- Snapshot `frontend/src/pages/login.tsx`, `register.tsx`, `dashboard.tsx`, `components/SQLQueryOptimizer.tsx`, `api/dashboardapi.ts` calls.
- Log broken flows: Google callback never parsed in `dashboard.tsx:1`, dead `googleLoginUser` in `api/authapi.ts:8`, `getConnections()` missing pagination.

Accept: baseline tests green, bug list filed as issues. Then PR → dual review → merge.

---

## Phase 1 — Config, App Factory, Security Foundation
**Branch:** `feature/phase-1-config-security` → PR to `developments`

Backend:
- New `src/config.py` (`pydantic-settings`): `SECRET_KEY>=32B` fail-fast in prod (remove auto-generate fallback in `backend/app.py:23`), require `ENCRYPTION_KEY`, `DATABASE_URL`, `ALLOWED_ORIGINS`, `RATE_LIMIT_PER_MIN`, `REDIS_URL`, `API_KEY_PROVIDER`.
- New `src/extensions.py`: db, migrate, cors, limiter, oauth init. Tighten CORS (no `*` with credentials).
- New `src/common/`: `ApiError`, `envelope()`, pagination, `request_id` logging.
- Fix `GET /health` (`backend/app.py:76`): reuse `db.engine`, add `GET /ready` (DB+Redis+LLM ping).
- Per-route rate limits: strict on auth/OTP, loose on reads.

Frontend:
- Centralize `VITE_API_URL`, add `request_id` header, global 401 → logout redirect, health badge.

Accept: restart doesn't break decrypt; health 200 without new engine per call; CORS + limiter verified. Then PR → dual review → merge.

---

## Phase 2 — Auth Revamp (localStorage JWT kept)
**Branch:** `feature/phase-2-auth` → PR to `developments`

Backend (`backend/auths/auth.py:75`, `backend/security/dec.py:6`):
- New `auth/jwt_service.py`: access (15min) + refresh (7d, rotation, `jti` denylist in Redis). Response shape `{token, refreshToken, user}` stays `localStorage`-compatible.
- Remove session fallback for `/api/*`; keep cookie only for OAuth browser step. Uniform JSON errors.
- OTP: require Redis in prod (`backend/auths/otp_store.py:62`), `secrets.compare_digest`, resend cooldown 60s, max 5 attempts, generic messages to stop enumeration. Replace `_print_otp` (`backend/auths/tasks.py:62`) with email interface + dev-only print behind `OTP_EMAIL_BACKEND=print`.
- Endpoints (new, keep old as shim):
  - `POST /api/v1/auth/register | login | refresh | logout | me`
  - `POST /api/v1/auth/forgot-password | verify-otp | reset-password | resend-otp`
  - `GET /api/v1/auth/oauth/google | /oauth/callback`

Frontend:
- Fix `dashboard.tsx`: parse `?token&user`, save via `saveToken/saveUser` (`frontend/src/api/authapi.ts:24`), clean URL.
- Delete/fix `googleLoginUser`. Add refresh interceptor: on 401 try `refresh` once, else logout.
- Add CSP meta, document XSS trade-off of `localStorage` in README.

Accept: multi-worker OTP passes; refresh rotation works; Google login end-to-end. Then PR → dual review → merge.

---

## Phase 3 — Connections Domain
**Branch:** `feature/phase-3-connections` → PR to `developments`

Backend (`backend/ai_dashboard/db_connections.py:15`, `backend/ai_dashboard/routes.py:106`):
- Split `connections/`: `model.py` (from `backend/auths/models.py:20`), `crypto.py` (versioned Fernet), `pool_manager.py` (single `QueuePool`, TTL+LRU, `dispose`), `service.py` (ownership checks), `schemas.py`.
- Fix drivers: add `pymysql`, map `postgresql+psycopg2://`, `mysql+pymysql://`, validate `connect_args` per dialect. Unify SSL handling.
- Fix Timer leak: replace `threading.Timer` per pool with lazy expiry + explicit `close`.
- Bound schema cache (max keys, 10min TTL).
- Endpoints:
  - `GET /api/v1/connections?page&per_page` → `{data, page, per_page, total}`
  - `POST /api/v1/connections`, `GET /api/v1/connections/:id`, `DELETE /api/v1/connections/:id`, `POST /api/v1/connections/:id/test`, `GET /api/v1/connections/:id/tables|schema`

Frontend:
- Update `DBConnectionForm.tsx`, `SavedConnections.tsx`, `dashboardapi.ts` to new routes + pagination. Show `last_used`, decrypt errors clearly.

Accept: save → test → list → select → delete round-trip on Postgres + MySQL; restart preserves credentials. Then PR → dual review → merge.

---

## Phase 4 — AI Platform: LCEL + LangGraph (learning path)
**Branch:** `feature/phase-4-ai-agent` → PR to `developments`

Backend (`backend/ai_dashboard/chains/agent_chain.py:176`, `backend/ai_dashboard/chains/sql_chain.py:101`, `backend/ai_dashboard/chains/introspection_chain.py:220`, `backend/ai_dashboard/tools/introspection.py:1`):
- `ai/llm_factory.py`: keep provider registry (`backend/settings.py:7`), add fallbacks, retries, timeout, LangSmith tracing, usage log.
- `ai/prompts/`: `sql_system.jinja`, `agent_system.jinja`, `few_shots.yaml`. Delete hardcoded `portfolio_*` examples (`agent_chain.py:99`).
- `ai/guards.py`: AST check via `sqlglot` (allow `SELECT/WITH` only), improved write-intent (not bare regex like `write_guard.py:3`), row `LIMIT 50`, `statement_timeout`.
- `ai/tools/`: `StructuredTool` wrappers with Pydantic args, allowlist table names from `information_schema`, JSON-safe rows.
- `ai/agents/`:
  - `sql_chain.py` — LCEL `prompt | llm.with_structured_output | safety_gate`. Keep for `mode=sql`, heavily commented for learning.
  - `react_agent.py` — LangGraph `create_react_agent`, max 6 steps, returns `{answer, toolCalls, usage}`. Main path for `mode=auto`.
  - Keep hand-rolled loop only as fallback when model lacks `bind_tools`.
- Delete dead `_metadata_handler/_data_handler` regex branch.
- Endpoint: `POST /api/v1/ai/query {query, connection_id, mode: auto|sql|answer}` → `{type: query|answer, sql?, answer?, rows?, count?, tables?, toolCalls?, usage?}`. Keep `POST /api/sql-query/` shim.
- Golden eval set (10 queries: list tables, count, join, refuse INSERT).

Frontend (`frontend/src/components/SQLQueryOptimizer.tsx:17`):
- Send `mode`, render `query` vs `answer` branches, rows table, collapsible `toolCalls` (helps learn LangGraph flow), usage badge.

Accept: evals pass, write intents refused without tool calls, traces visible in UI + LangSmith. Then PR → dual review → merge.

---

## Phase 5 — API Versioning & Contract Lock
**Branch:** `feature/phase-5-api-contract` → PR to `developments`

- Mount all new routes under `/api/v1`, keep old with deprecation header + shim layer.
- Standard envelope `{success, data, error:{code,message}}`, pagination envelope, OpenAPI at `/openapi.json`.
- Rewrite `dashboardapi.ts` fully versioned, update `types/auth.ts`, `types/connection.ts`.
- Rewrite `API_REFERENCE.md`, frontend `.env.example` (`VITE_API_URL`).

Accept: `tsc` + contract tests against `/api/v1` green; old routes log deprecation warning. Then PR → dual review → merge.

---

## Phase 6 — Quality, Tests, Deploy
**Branch:** `feature/phase-6-quality-deploy` → PR to `developments`

- Backend: `pytest` unit+integration (auth, connections, guards, agent with mocked LLM), coverage gate.
- Frontend: add `vitest` smoke for api clients + Optimizer states.
- CI: lint → test → build. Dockerfile multi-stage, non-root, `gunicorn` pinned. Fix root `vercel.json:2` (point to `frontend/`), verify `apprunner.yaml:8` health path `/health`.
- Docs: runbook, key rotation, Redis/Celery setup.

Accept: CI green, staging deploy + health/ready OK, Vercel preview OK. Then PR → dual review → merge.

---

## Phase 7 — Migration & Rollout
**Branch:** `feature/phase-7-rollout` → PR to `developments`

- Re-encrypt existing `db_connections` with new `ENCRYPTION_KEY` version; force re-login for JWT rotation.
- Stage → prod cutover, monitor logs (`toolCalls`, LLM latency, pool stats).
- Remove old unversioned routes + dead code (`create_connection` raw path in `backend/ai_dashboard/db_connections.py:424` if unused).
- Close-out: update `AGENT.md` if conventions changed.

Accept: prod smoke (register → connect → query → answer) passes; no P0 open. Then final PR → dual review → merge → tag release.

---

## Appendix A — P0/P1 bug register (must be zero before merge of owning phase)

- P0: ephemeral `SECRET_KEY` breaks Fernet decrypt (`app.py:23`, `crypto.py:6`) → Phase 1/3
- P0: `MemoryOTPStore` fails with `gunicorn -w 4` (`Dockerfile:19`) → Phase 2
- P0: Google OAuth callback never parsed (`dashboard.tsx:1`), dead `googleLoginUser` (`authapi.ts:8`) → Phase 2
- P1: token in URL leaks; session+JWT mix (`dec.py:31`); OTP stdout leak (`tasks.py:62`); naive `write_guard.py:3`; hardcoded `portfolio_*` (`agent_chain.py:99`); dead router branches (`introspection_chain.py:84,122`); Timer/pool races (`db_connections.py:15`); missing `pymysql`; health new-engine per call (`app.py:76`); `vercel.json:2` root build broken

## Appendix B — Endpoint map (old → new)

| Today | New |
|---|---|
| `POST /auth/register`, `POST /auth/login`, `GET /auth/login`, `GET /auth/callback` | `POST /api/v1/auth/register`, `login`, `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`, `GET /api/v1/auth/oauth/google`, `GET /api/v1/auth/oauth/callback` |
| `POST /auth/forgot-password`, `verify-otp`, `reset-password` | Same under `/api/v1/auth/` + `POST /resend-otp` |
| `POST /api/db-connection`, `GET /api/get-connections/`, `POST /api/test-connection/`, `DELETE /api/delete-connection` | `GET/POST /api/v1/connections`, `GET/DELETE /api/v1/connections/:id`, `POST /api/v1/connections/:id/test`, `GET /api/v1/connections/:id/tables\|schema` |
| `POST /api/sql-query/` | `POST /api/v1/ai/query` (shim kept until Phase 7) |
