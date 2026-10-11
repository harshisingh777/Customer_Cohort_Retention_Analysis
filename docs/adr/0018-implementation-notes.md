# 18. Implementation notes and deviations from the spec

Status: accepted

| Spec | Built | Why |
|---|---|---|
| uv workspace with a shared `core` package | One uv project with dependency groups (`api`, `pipeline`, `dev`); `core/` is a top-level package | Same per-image dependency separation with less packaging; each image installs only its group |
| Staging incremental | Staging rebuilt each run | See ADR 9 |
| Ramp step 5 `#5584B3` | `#4A79A8` | See ADR 12 |
| TanStack Table "current stable" | v8.21 | v9 changed its API; v8 is the newest release whose API was verified here |
| Generated client (orval or openapi-typescript) | openapi-typescript types plus a typed route map | Fewer moving parts; CI fails on drift of `apps/api/openapi.json` and `schema.d.ts` |
| `postcss` latest | 8.5.28 | 8.5.29 was published inside pnpm's minimum-release-age window, which the lockfile policy rejects |
| "Repeat within 90 days" | Days 0-89 after the first order; eligible when the first order is at least 90 days before the cutoff | Makes the window and LTV-at-90 consistent and fully observed |
| `/customers` list route | Added `GET /v1/customers` beside `/segments/{segment}/customers` | The Customers page lists everyone with segment and status filters |
| Users and invites | Added `GET/POST/PATCH/DELETE /v1/users` (admin) | The phase 6 invite flow needs it |
| Findings baseline interval | Wilson interval at the median rate, for the baseline cohorts' average size | The spec says "outside the 95% interval of the comparison baseline" without fixing n; the rule is written in `metrics.yml` |
| Spec example "24.0-28.9%" | The exact Wilson interval for 318/1,204 is 24.00-28.97% | The illustration truncates; tests check the exact interval |
| Video walkthrough (handoff) | `docs/walkthrough.md` script | A recording can't be produced from the repository |
