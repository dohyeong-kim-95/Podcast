from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row


def _db_url() -> str:
    value = os.getenv("SUPABASE_DB_URL", "").strip()
    if not value:
        raise RuntimeError("SUPABASE_DB_URL not configured")
    return value


@contextmanager
def get_db() -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(_db_url(), row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def serialize_timestamp(value: Any) -> str | None:
    if value and hasattr(value, "isoformat"):
        normalized = value if getattr(value, "tzinfo", None) else value.replace(tzinfo=timezone.utc)
        return normalized.isoformat()
    return None


def serialize_date(value: Any) -> str | None:
    if isinstance(value, date):
        return value.isoformat()
    return None

