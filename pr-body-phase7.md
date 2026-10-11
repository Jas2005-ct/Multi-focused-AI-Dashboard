## Scope (Phase 7 — plan.md)

- Migration scripts for production rollout:
  - `migrate_encryption.py`: Re-encrypt all DB connections with new ENCRYPTION_KEY version
  - `migrate_invalidate_tokens.py`: Invalidate all refresh tokens to force re-login
  - `cleanup_dead_code.py`: Documentation of dead code removed in Phase 7
- Verified migration scripts work with test database (0 connections migrated, 0 tokens revoked in clean test DB)
- All existing tests pass (48/48)
- Frontend builds clean (tsc + eslint)

## Test evidence

- backend pytest: 48 passed
- migration scripts run without errors (tested on clean SQLite DB)
- frontend build: tsc + eslint clean

## Breaking changes

- None (migration scripts are additive, run manually during rollout)

## Rollback

- Revert single commit e5be224