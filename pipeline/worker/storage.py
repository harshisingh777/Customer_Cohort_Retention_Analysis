"""Export file storage. S3-compatible object storage when S3_BUCKET is set, otherwise
Postgres (ops.export_files). Never the service's local disk."""

from __future__ import annotations

from core.config import get_env
from core.db import Conn


def store(conn: Conn, export_id: str, content: bytes, content_type: str) -> tuple[str, str]:
    env = get_env()
    if env.s3_bucket:
        import boto3

        key = f"exports/{export_id}.pdf"
        boto3.client(
            "s3", endpoint_url=env.s3_endpoint_url or None, region_name=env.s3_region or None
        ).put_object(Bucket=env.s3_bucket, Key=key, Body=content, ContentType=content_type)
        return "s3", key
    conn.execute(
        "insert into ops.export_files (export_id, content, content_type) values (%s, %s, %s) "
        "on conflict (export_id) do update set content = excluded.content",
        (export_id, content, content_type),
    )
    return "db", export_id
