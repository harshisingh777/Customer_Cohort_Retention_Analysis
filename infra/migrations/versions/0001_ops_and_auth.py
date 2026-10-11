"""ops and auth schemas, PII access function, role grants

Revision ID: 0001
Revises:
Create Date: 2026-10-05
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        create schema if not exists ops;
        create schema if not exists auth;

        -- Store settings that change metric definitions. Defaults live in core/store_settings.py.
        create table ops.settings (
          key         text primary key,
          value       jsonb not null,
          updated_at  timestamptz not null default now(),
          updated_by  text
        );

        -- Invite-only allowlist.
        create table ops.users (
          email         text primary key check (email = lower(email)),
          role          text not null check (role in ('admin', 'viewer')),
          name          text,
          invited_by    text,
          invited_at    timestamptz not null default now(),
          last_seen_at  timestamptz,
          disabled      boolean not null default false
        );

        create table ops.jobs (
          id             bigserial primary key,
          kind           text not null check (kind in ('refresh', 'clv_fit', 'pdf_export')),
          payload        jsonb not null default '{}'::jsonb,
          status         text not null default 'queued'
                         check (status in ('queued', 'running', 'succeeded', 'failed')),
          scheduled_for  timestamptz not null default now(),
          run_after      timestamptz not null default now(),
          attempts       int not null default 0,
          max_attempts   int not null default 3,
          locked_at      timestamptz,
          locked_by      text,
          error          text,
          created_by     text,
          created_at     timestamptz not null default now(),
          finished_at    timestamptz,
          unique (kind, scheduled_for)
        );
        create index jobs_claim_idx on ops.jobs (status, run_after) where status = 'queued';

        create table ops.pipeline_runs (
          id              bigserial primary key,
          job_id          bigint references ops.jobs(id) on delete set null,
          kind            text not null,
          trigger         text not null,
          status          text not null check (status in ('running', 'published', 'failed')),
          started_at      timestamptz not null default now(),
          finished_at     timestamptz,
          steps           jsonb not null default '[]'::jsonb,
          tests           jsonb,
          reconciliation  jsonb,
          row_counts      jsonb,
          error           text,
          data_version    text
        );
        create index pipeline_runs_started_idx on ops.pipeline_runs (started_at desc);

        create table ops.data_versions (
          version       text primary key,
          run_id        bigint references ops.pipeline_runs(id) on delete set null,
          data_through  date not null,
          published_at  timestamptz not null default now()
        );
        create index data_versions_published_idx on ops.data_versions (published_at desc);

        create table ops.ingest_cursors (
          source        text not null,
          entity        text not null,
          cursor_value  text not null,
          updated_at    timestamptz not null default now(),
          primary key (source, entity)
        );

        create table ops.ingest_batches (
          batch_id       uuid primary key,
          source         text not null,
          entity         text not null,
          started_at     timestamptz not null default now(),
          finished_at    timestamptz,
          rows_in        int not null default 0,
          rows_upserted  int not null default 0,
          rows_dropped   int not null default 0,
          drop_reasons   jsonb not null default '{}'::jsonb
        );
        create index ingest_batches_started_idx on ops.ingest_batches (started_at desc);

        create table ops.audit_log (
          id      bigserial primary key,
          at      timestamptz not null default now(),
          actor   text not null,
          action  text not null,
          detail  jsonb not null default '{}'::jsonb
        );

        create table ops.exports (
          id           uuid primary key default gen_random_uuid(),
          owner        text not null,
          format       text not null check (format in ('pdf')),
          view         text not null,
          params       jsonb not null default '{}'::jsonb,
          status       text not null default 'queued'
                       check (status in ('queued', 'running', 'succeeded', 'failed')),
          job_id       bigint references ops.jobs(id) on delete set null,
          storage      text check (storage in ('s3', 'db')),
          storage_key  text,
          error        text,
          created_at   timestamptz not null default now(),
          finished_at  timestamptz
        );

        create table ops.export_files (
          export_id     uuid primary key references ops.exports(id) on delete cascade,
          content       bytea not null,
          content_type  text not null,
          created_at    timestamptz not null default now()
        );

        -- Email masking for viewers. Admins see the full address.
        create function ops.mask_email(e text) returns text
        language sql immutable as $$
          select case
            when e is null or position('@' in e) = 0 then null
            else left(e, 1) || '***' || substr(e, position('@' in e))
          end
        $$;

        -- The only path from the API to customer emails. pii.* is rebuilt by dbt on each publish,
        -- so the body is plpgsql (resolved at call time, not at creation).
        create function ops.customer_contacts(p_keys text[], p_reveal boolean)
        returns table (customer_key text, email text)
        language plpgsql stable security definer
        set search_path = pg_catalog, pii
        as $$
        begin
          return query
            select c.customer_key,
                   case when p_reveal then c.email else ops.mask_email(c.email) end
            from pii.customer_contacts c
            where c.customer_key = any(p_keys);
        exception when undefined_table or invalid_schema_name then
          return;
        end
        $$;
        -- Owned by pipeline_rw (owner of pii.*). The new owner needs CREATE on ops only for the change.
        grant create on schema ops to pipeline_rw;
        alter function ops.customer_contacts(text[], boolean) owner to pipeline_rw;
        revoke create on schema ops from pipeline_rw;
        revoke all on function ops.customer_contacts(text[], boolean) from public;

        -- Auth.js (pg adapter) tables. JWT sessions, so `sessions` stays empty.
        create table auth.users (
          id               serial primary key,
          name             varchar(255),
          email            varchar(255),
          "emailVerified"  timestamptz,
          image            text
        );
        create table auth.accounts (
          id                   serial primary key,
          "userId"             integer not null,
          type                 varchar(255) not null,
          provider             varchar(255) not null,
          "providerAccountId"  varchar(255) not null,
          refresh_token        text,
          access_token         text,
          expires_at           bigint,
          id_token             text,
          scope                text,
          session_state        text,
          token_type           text
        );
        create table auth.sessions (
          id              serial primary key,
          "userId"        integer not null,
          expires         timestamptz not null,
          "sessionToken"  varchar(255) not null
        );
        create table auth.verification_token (
          identifier  text not null,
          expires     timestamptz not null,
          token       text not null,
          primary key (identifier, token)
        );
        -- One-time tokens for the PDF print route.
        create table auth.print_tokens (
          jti      text primary key,
          used_at  timestamptz not null default now()
        );

        -- Grants --------------------------------------------------------------
        grant usage on schema ops to pipeline_rw, api_ro, api_ops, web_auth;

        grant select, insert, update, delete on
          ops.jobs, ops.pipeline_runs, ops.data_versions, ops.ingest_cursors,
          ops.ingest_batches, ops.exports, ops.export_files
          to pipeline_rw;
        grant select, insert on ops.settings, ops.users, ops.audit_log to pipeline_rw;
        grant update on ops.settings to pipeline_rw;
        grant usage on all sequences in schema ops to pipeline_rw;

        grant select on
          ops.settings, ops.users, ops.jobs, ops.pipeline_runs, ops.data_versions,
          ops.ingest_batches, ops.exports, ops.export_files
          to api_ro;
        grant execute on function ops.customer_contacts(text[], boolean) to api_ro;
        grant execute on function ops.mask_email(text) to api_ro, pipeline_rw;

        grant select, insert on ops.jobs, ops.exports, ops.audit_log to api_ops;
        grant select, insert, update on ops.settings, ops.users to api_ops;
        grant delete on ops.users to api_ops;
        grant usage on all sequences in schema ops to api_ops;

        grant usage on schema auth to web_auth;
        grant select, insert, update, delete on all tables in schema auth to web_auth;
        grant usage on all sequences in schema auth to web_auth;
        grant select on ops.users to web_auth;
        grant update (last_seen_at) on ops.users to web_auth;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        drop schema auth cascade;
        drop function if exists ops.customer_contacts(text[], boolean);
        drop function if exists ops.mask_email(text);
        drop table if exists ops.export_files, ops.exports, ops.audit_log, ops.ingest_batches,
          ops.ingest_cursors, ops.data_versions, ops.pipeline_runs, ops.jobs, ops.users,
          ops.settings cascade;
        """
    )
