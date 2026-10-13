"""The demo inbox as a snapshot: every table's rows as JSON, model responses included.

The snapshot is built once with live model calls (scripts/build_demo.py) and committed.
Loading it fills any database (SQLite or Postgres) with analysed emails, risk runs and drafts,
plus the cached model responses behind them. The demo therefore works without a single
live call: when the API key is missing, the network fails or the daily spend cap is
reached, re-running a demo step is answered from the cache.

Generated documents are not in the snapshot (their PDFs live on disk); the demo story
generates them live, which needs no model call.
"""

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Date, DateTime, Numeric, Table, func, select, text
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR
from app import models  # noqa: F401  (registers every table on Base.metadata)
from app.db import Base

SNAPSHOT_PATH = BACKEND_DIR / "demo" / "snapshot.json"
# Rows that only make sense on the machine that made them.
_SKIPPED = {"documents"}


def _tables() -> list[Table]:
    return [t for t in Base.metadata.sorted_tables if t.name not in _SKIPPED]


def _plain(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def export_snapshot(session: Session) -> dict[str, Any]:
    tables = {}
    for table in _tables():
        rows = session.execute(select(table).order_by(*table.primary_key.columns)).mappings()
        tables[table.name] = [{key: _plain(value) for key, value in row.items()} for row in rows]
    return {"format": 1, "created": datetime.now().isoformat(timespec="seconds"), "tables": tables}


def _typed(table: Table, row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for column in table.columns:
        if column.name not in row:
            continue
        value = row[column.name]
        if value is not None:
            if isinstance(column.type, DateTime):
                value = datetime.fromisoformat(value)
            elif isinstance(column.type, Date):
                value = date.fromisoformat(value)
            elif isinstance(column.type, Numeric):
                value = Decimal(value)
        out[column.name] = value
    return out


def load_snapshot(session: Session, snapshot: dict[str, Any]) -> dict[str, int]:
    """Replace everything in the database with the snapshot. Returns rows per table."""
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    counts = {}
    for table in _tables():
        rows = [_typed(table, row) for row in snapshot["tables"].get(table.name, [])]
        if table.name == "llm_calls":
            # The calls that built the demo stay visible in the trace but are not today's spend.
            rows = [row | {"source": "snapshot"} if row.get("source") == "live" else row for row in rows]
        if rows:
            session.execute(table.insert(), rows)
        counts[table.name] = len(rows)
    session.flush()
    if session.bind.dialect.name == "postgresql":
        # Explicit ids were inserted: move each id sequence past them.
        for table in _tables():
            if "id" in table.columns:
                session.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table.name}), 0) + 1, false)"
                ))
    session.commit()
    return counts


def read_snapshot(path: Path = SNAPSHOT_PATH) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def is_empty(session: Session) -> bool:
    from app.models import Email

    return (session.scalar(select(func.count()).select_from(Email)) or 0) == 0
