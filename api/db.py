"""One table. Results are JSONB because the check list changes weekly and a
normalised schema would be migration churn for no query benefit."""
from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id           TEXT PRIMARY KEY,
    url          TEXT NOT NULL,
    brand_name   TEXT,
    email        TEXT,
    status       TEXT NOT NULL DEFAULT 'audited',
    page_excerpt TEXT,
    audit_json   JSONB,
    visibility_json JSONB,
    lead_json    JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

ALPHABET = "23456789abcdefghijkmnpqrstuvwxyz"  # no look-alikes; these ids go in URLs


def new_id(n: int = 10) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(n))


class MemoryStore:
    """Local-dev fallback so the app runs with no database.

    # ponytail: process-local dict, dies on restart. Set DATABASE_URL for anything real.
    """

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    async def connect(self) -> None: ...
    async def close(self) -> None: ...

    async def create(self, **row) -> None:
        self.rows[row["id"]] = {"created_at": datetime.now(timezone.utc), **row}

    async def get(self, scan_id: str) -> dict | None:
        return self.rows.get(scan_id)

    async def update(self, scan_id: str, **fields) -> None:
        if scan_id in self.rows:
            self.rows[scan_id].update(fields)


class PostgresStore:
    def __init__(self, dsn: str) -> None:
        self.dsn, self.pool = dsn, None

    async def connect(self) -> None:
        import asyncpg

        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5)
        async with self.pool.acquire() as conn:
            await conn.execute(SCHEMA)

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    async def create(self, **row) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO scans (id, url, brand_name, status, page_excerpt, audit_json)
                   VALUES ($1,$2,$3,$4,$5,$6)""",
                row["id"], row["url"], row.get("brand_name"), row.get("status", "audited"),
                row.get("page_excerpt"), json.dumps(row.get("audit_json")),
            )

    async def get(self, scan_id: str) -> dict | None:
        async with self.pool.acquire() as conn:
            rec = await conn.fetchrow("SELECT * FROM scans WHERE id = $1", scan_id)
        if not rec:
            return None
        row = dict(rec)
        for key in ("audit_json", "visibility_json", "lead_json"):
            if isinstance(row.get(key), str):
                row[key] = json.loads(row[key])
        return row

    async def update(self, scan_id: str, **fields) -> None:
        if not fields:
            return
        cols, values = [], []
        for i, (k, v) in enumerate(fields.items(), start=2):
            cols.append(f"{k} = ${i}")
            values.append(json.dumps(v) if k.endswith("_json") else v)
        async with self.pool.acquire() as conn:
            await conn.execute(f"UPDATE scans SET {', '.join(cols)} WHERE id = $1", scan_id, *values)


def make_store() -> Any:
    dsn = os.getenv("DATABASE_URL")
    return PostgresStore(dsn) if dsn else MemoryStore()
