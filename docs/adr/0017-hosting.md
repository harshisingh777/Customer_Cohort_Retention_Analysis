# 17. Always-on instances; nothing on local disk

Status: accepted

## Decision
Web on Vercel; API and worker as two always-on small instances (`infra/render.yaml`); managed
Postgres with point-in-time restore. Free tiers that sleep or wipe disks are not used in
production. Export files go to S3-compatible storage when `S3_BUCKET` is set, otherwise to
`ops.export_files`; dbt artefacts live in a temporary directory per run; datasets are cached in
`data/` for local seeding only.
