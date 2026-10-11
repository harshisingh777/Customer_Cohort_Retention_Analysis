-- Database roles. Run once per database as a superuser / owner:
--   psql "$ADMIN_URL" -v dbname=retention -v migrator_password=... -v pipeline_password=... \
--        -v api_ro_password=... -v api_ops_password=... -v web_auth_password=... -f infra/db/roles.sql
-- Idempotent: safe to re-run to rotate passwords.
\set ON_ERROR_STOP on

create extension if not exists pgcrypto;

do $$
begin
  if not exists (select from pg_roles where rolname = 'migrator')    then create role migrator    login; end if;
  if not exists (select from pg_roles where rolname = 'pipeline_rw') then create role pipeline_rw login; end if;
  if not exists (select from pg_roles where rolname = 'api_ro')      then create role api_ro      login; end if;
  if not exists (select from pg_roles where rolname = 'api_ops')     then create role api_ops     login; end if;
  if not exists (select from pg_roles where rolname = 'web_auth')    then create role web_auth    login; end if;
end
$$;

alter role migrator    password :'migrator_password';
alter role pipeline_rw password :'pipeline_password';
alter role api_ro      password :'api_ro_password';
alter role api_ops     password :'api_ops_password';
alter role web_auth    password :'web_auth_password';

-- migrator owns ops/auth and creates the security-definer PII function owned by pipeline_rw.
grant pipeline_rw to migrator;
grant create on database :"dbname" to migrator, pipeline_rw;

-- The API reads marts only; long queries must never block a publish.
alter role api_ro  set statement_timeout = '5s';
alter role api_ops set statement_timeout = '5s';
alter role web_auth set search_path = auth;
alter role web_auth set statement_timeout = '5s';

-- Nobody but the owner creates objects in public.
revoke create on schema public from public;
