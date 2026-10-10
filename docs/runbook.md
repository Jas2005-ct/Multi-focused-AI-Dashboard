# AI Dashboard — Operations Runbook

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌────────────────────┐
│   Frontend      │────▶│   Backend API    │────▶│  PostgreSQL        │
│  (Nginx/React)  │     │  (Flask/Gunicorn)│     │  (User/Connection) │
└─────────────────┘     └──────────────────┘     └────────────────────┘
                              │
                              ▼
                       ┌──────────────────┐
                       │   Redis          │
                       │  (OTP/Celery)    │
                       └──────────────────┘
```

## Quick Start (Local Dev)

```bash
# Backend
cd backend
uv sync
cp .env.example .env  # Edit with your keys
.venv/bin/flask --app "app:create_app()" db upgrade
.venv/bin/flask --app "app:create_app()" run --debug

# Frontend (separate terminal)
cd frontend
npm ci
npm run dev
```

## Environment Variables

### Required (Production)
| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | Flask secret, ≥32 bytes | `openssl rand -base64 32` |
| `ENCRYPTION_KEY` | Fernet key for DB passwords, ≥32 bytes | `openssl rand -base64 32` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host:5432/db` |
| `ENCRYPTION_KEY_V2` | (Optional) Key rotation | `openssl rand -base64 32` |
| `REDIS_URL` | Redis for OTP/Celery | `redis://localhost:6379/0` |

### Optional / Dev
| Variable | Default | Notes |
|----------|---------|-------|
| `FLASK_ENV` | `development` | Set to `production` in prod |
| `OTP_BACKEND` | `memory` | Use `redis` in prod |
| `OTP_EMAIL_BACKEND` | `auto` | `celery` or `print` |
| `API_KEY_PROVIDER` | `OPEN_ZEN` | `OPEN_ZEN` or `OPENROUTER` |
| `OPEN_ZEN_API_KEY` | — | For LLM via OpenCode Zen |
| `OPEN_ROUTER_API_KEY` | — | For LLM via OpenRouter |

## Key Rotation

### SECRET_KEY / ENCRYPTION_KEY
1. Generate new keys:
   ```bash
   NEW_SECRET=$(openssl rand -base64 32)
   NEW_ENCRYPTION=$(openssl rand -base64 32)
   ```
2. Add as `ENCRYPTION_KEY_V2` (or `V3`, etc.) — old keys still decrypt
3. Deploy with new primary keys
4. Re-encrypt stored credentials (see below)
5. Remove old key version after verification

### Re-encrypt DB Credentials
```bash
# One-off script to re-encrypt all DB connections
cd backend
.venv/bin/python -c "
from app import create_app
from connections.service import list_connections
from connections.crypto import crypto
from auths.models import db, DBConnection

app = create_app()
with app.app_context():
    for conn in DBConnection.query.all():
        # Decrypt with old key, encrypt with new
        pw = crypto.decrypt(conn.password)
        cs = crypto.decrypt(conn.connection_string)
        conn.password = crypto.encrypt(pw)
        conn.connection_string = crypto.encrypt(cs)
        db.session.add(conn)
    db.session.commit()
    print('Re-encrypted', DBConnection.query.count(), 'connections')
"
```

## Deployment

### Backend (AWS App Runner / Docker)
```dockerfile
# Build
docker build -t ai-dashboard-backend ./backend

# Run
docker run -d \
  -p 8000:8000 \
  -e SECRET_KEY=... \
  -e ENCRYPTION_KEY=... \
  -e DATABASE_URL=... \
  -e REDIS_URL=... \
  ai-dashboard-backend
```

### Frontend (Vercel / Docker)
```dockerfile
docker build -t ai-dashboard-frontend ./frontend
```

### Vercel Configuration
```json
// vercel.json
{
  "buildCommand": "cd frontend && npm run build",
  "outputDirectory": "frontend/dist",
  "installCommand": "cd frontend && npm ci",
  "framework": "vite",
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

## Health & Readiness

| Endpoint | Purpose | Expected |
|----------|---------|----------|
| `GET /health` | Liveness (LB) | `{"status":"ok","database":"connected"}` |
| `GET /ready` | Readiness (K8s/LB) | `{"status":"ready","checks":{"database":"connected"}}` |
| `GET /openapi.json` | OpenAPI 3.0 spec | Full spec |

## Common Operations

### View Logs
```bash
# Backend (Docker)
docker logs -f <container>

# App Runner
aws apprunner get-log --service-arn <arn>
```

### Database Migrations
```bash
# Create migration
cd backend
.venv/bin/flask --app "app:create_app()" db migrate -m "description"

# Apply
.venv/bin/flask --app "app:create_app()" db upgrade
```

### Reset Password (Admin)
```bash
# Via backend CLI
cd backend
.venv/bin/python -c "
from app import create_app
from auths.models import db, User
from werkzeug.security import generate_password_hash

app = create_app()
with app.app_context():
    u = User.query.filter_by(email='admin@example.com').first()
    u.password = generate_password_hash('NewPass123')
    db.session.commit()
    print('Password reset for', u.email)
"
```

### Clear OTP Store (Redis)
```bash
redis-cli -u $REDIS_URL KEYS "otp:*" | xargs redis-cli DEL
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `SECRET_KEY` error on startup | Key < 32 bytes | Set proper `SECRET_KEY` in env |
| `Invalid token` on refresh | Refresh token expired/revoked | User must re-login |
| `422` on `/api/sql-query/` | Body validation failed | Check `sentence` not empty, `db_id` is int |
| `Connection failed` | Wrong creds / network | Verify `DATABASE_URL`, security groups |
| `ModuleNotFoundError: sqlglot` | Missing dep | `uv add sqlglot` |
| Frontend 404 on refresh | SPA fallback missing | Ensure Vercel rewrites / nginx config |

## Key Metrics to Monitor

| Metric | Target | Alert If |
|--------|--------|----------|
| API latency (p95) | < 500ms | > 2s |
| DB connection pool usage | < 70% | > 90% |
| Redis memory | < 100MB | > 500MB |
| Error rate | < 0.1% | > 1% |
| Gunicorn workers | 4 | Worker crashes > 5/min |

## Incident Response

1. **API 5xx spike** → Check backend logs, DB connectivity, LLM provider status
2. **Auth failures** → Verify `SECRET_KEY`, Redis connectivity, clock sync
3. **DB pool exhaustion** → Check for connection leaks, increase pool size
4. **Frontend 404s** → Verify SPA rewrite rules, check build output

## Backup & Recovery

- **PostgreSQL**: Daily automated snapshots (RDS) / `pg_dump` daily
- **Redis**: RDB snapshots every 5 min (AOF enabled)
- **Secrets**: Store in AWS Secrets Manager / Vault, rotate quarterly

---

*Last updated: 2026-10-10 | Version: Phase 6*