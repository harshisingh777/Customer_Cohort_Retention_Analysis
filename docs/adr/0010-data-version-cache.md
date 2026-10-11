# 10. Data-version keyed cache and ETags

Status: accepted

## Decision
The API keeps the current data version in memory (LISTEN on a direct connection, 30-second poll
as fallback). Responses are cached in-process (LRU), keyed by (data version, route, normalised
params, and role where emails differ). `ETag = hash(key)`; a matching `If-None-Match` returns 304.
`Cache-Control: private, max-age=60, stale-while-revalidate=600`. Brotli/gzip over 1 KB.
Routes that change without a publish (meta freshness, data health, settings) use content-hashed
ETags instead. Query keys in the web app include the data version, so a publish refetches
everything once.

## Consequences
Warm requests come from memory. Measured on seed data: cache misses 7-65 ms, 304s about 2 ms.
