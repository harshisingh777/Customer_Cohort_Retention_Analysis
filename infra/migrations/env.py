"""Alembic environment. Alembic owns the ops and auth schemas and nothing else."""

from alembic import context
from sqlalchemy import create_engine, text

from core.config import get_env, to_psycopg_url

url = to_psycopg_url(get_env().migrator_database_url).replace(
    "postgresql://", "postgresql+psycopg://", 1
)


def run_migrations_online() -> None:
    engine = create_engine(url)
    with engine.connect() as connection:
        connection.execute(text("create schema if not exists ops"))
        connection.commit()
        context.configure(
            connection=connection,
            version_table_schema="ops",
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    context.configure(url=url, literal_binds=True, version_table_schema="ops")
    with context.begin_transaction():
        context.run_migrations()
else:
    run_migrations_online()
