# 11. Session in the web app, short-lived JWT verified by the API, roles enforced in the API

Status: accepted

## Context
Next.js middleware-only auth has been bypassable (CVE-2025-29927). The API must not trust the
frontend.

## Decision
Auth.js v5 (magic link, plus Google when configured), invite-only via `ops.users`. The web server
mints a 5-minute HS256 JWT (`sub`, `role`, `exp`) with a key shared only with the API; the browser
gets it from a same-origin route and refreshes it 30 s before expiry. The API verifies every
request and takes the role from the allowlist (re-read every 60 s), not from the token: a viewer
who forges an "admin" claim is still a viewer, and a removed user loses access within a minute.
No middleware is used for auth. Database roles: `api_ro` (reads marts), `api_ops` (inserts jobs,
exports and audit rows; edits settings and users), `pipeline_rw`, `migrator`, `web_auth`.

## Consequences
Print tokens for PDFs are single-use: the worker mints one with `scope: print` and a `jti`, and
the print route redeems the `jti` in `auth.print_tokens` before rendering.
