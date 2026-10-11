# 13. Emails are keyed hashes (HMAC-SHA256) after staging

Status: accepted

## Decision
Staging replaces email with `HMAC-SHA256(lower(trim(email)), PII_KEY)`. The key reaches Postgres
as the session setting `retention.pii_key` via `PGOPTIONS`, so it never appears in compiled SQL,
dbt artefacts or query logs. Raw emails remain only in `raw` and in `pii.customer_contacts`,
which `api_ro` cannot read; the API reads emails only through the security-definer function
`ops.customer_contacts(keys, reveal)`, passing `reveal` only for admins.

## Consequences
Rotating `PII_KEY` re-keys guest-only customers (`e:` keys) on the next refresh; see the runbook.
