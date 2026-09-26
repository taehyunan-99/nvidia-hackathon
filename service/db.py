"""PostgreSQL connection and explicit schema preparation for the persistent service."""

from __future__ import annotations

from pathlib import Path
import os

import psycopg
from psycopg.rows import dict_row

MIGRATIONS = sorted((Path(__file__).parent / "migrations").glob("[0-9]*.sql"))


def connect(dsn: str) -> psycopg.Connection:
    return psycopg.connect(dsn, row_factory=dict_row)


def migrate(dsn: str) -> None:
    with connect(dsn) as conn:
        with conn.cursor() as cur:
            for migration in MIGRATIONS:
                cur.execute(migration.read_text(encoding="utf-8"))


def require_schema(dsn: str) -> None:
    with connect(dsn) as conn:
        row = conn.execute("SELECT version FROM schema_migrations WHERE version = 2").fetchone()
        if not row:
            raise RuntimeError("서비스 DB migration 002를 먼저 실행하세요.")


if __name__ == "__main__":
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL이 필요합니다.")
    migrate(dsn)
