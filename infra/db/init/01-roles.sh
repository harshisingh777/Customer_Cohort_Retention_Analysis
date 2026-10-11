#!/bin/sh
# Postgres container entrypoint hook (local dev and CI). Production runs roles.sql by hand.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v dbname="$POSTGRES_DB" \
  -v migrator_password="$MIGRATOR_PASSWORD" \
  -v pipeline_password="$PIPELINE_PASSWORD" \
  -v api_ro_password="$API_RO_PASSWORD" \
  -v api_ops_password="$API_OPS_PASSWORD" \
  -v web_auth_password="$WEB_AUTH_PASSWORD" \
  -f /docker-entrypoint-initdb.d/roles.sql.inc
