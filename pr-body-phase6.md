## Scope (Phase 6 — plan.md)

- Backend: pytest/ruff/black gates, coverage-ready (48/48 tests pass)
- Frontend: tsc/ESLint/vite build clean (8 remaining lint errors all in Phase-3/4-owned components)
- Docker: multi-stage backend (non-root, gunicorn pinned), frontend (nginx + SPA fallback)
- Deploy: vercel.json fixed (points to frontend/), apprunner.yaml verified (/health), Dockerfiles added
- CI: GitHub Actions workflow (.github/workflows/ci.yml) — **manual add required** due to OAuth scope; see PR description for full yaml
- Docs: runbook.md with key rotation, troubleshooting, metrics, backup/recovery

## Test evidence

- backend pytest: 48 passed
- ruff + black clean on touched files; tsc build green; eslint clean on touched files

## Breaking changes

- None intended

## Rollback

- Revert single commit 55ea813

## CI Workflow (Manual Add Required)

Due to OAuth scope limitations, the CI workflow file must be manually added to GitHub:

1. Go to Settings > Actions > General > Workflow permissions > "Allow GitHub Actions to create and approve pull requests"
2. Add `.github/workflows/ci.yml` with the content from the commit history (or create manually from the PR description)
3. Re-run PR checks