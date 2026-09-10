# Project Rules

## Pull Request Title Convention
All pull requests MUST follow the format:
- `To dev: <type>: <description>` when targeting the `developments` branch
- `To master: <type>: <description>` when targeting the `main` branch

Examples:
- `To dev: feat: tool-calling agent with secure read-only SQL execution`
- `To master: fix: correct pooled connection context manager`
- `To dev: docs: update API references`

This rule is enforced for all upcoming changes. PRs not following this format will be requested to retitle.

## Branch Naming
- `feature/*` for new features
- `improvements/*` / `improvments/*` for enhancements
- `fix/*` for bug fixes

## Commit Message Format
Use conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`
