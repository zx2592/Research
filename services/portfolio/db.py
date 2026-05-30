"""
PortfolioDatabase — SQLite 存储层

Append-only event store backed by SQLite.
Stores all portfolio events in a single `events` table.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List

from services.portfolio.events import (
    CashFlowEvent, EventType, FillEvent, PortfolioEvent, SplitEvent
)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS portfolio_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    TEXT NOT NULL UNIQUE,
    event_type  TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    payload     TEXT NOT NULL
)
"""


class PortfolioDatabase:
    """SQLite-backed append-only event store."""

    def __init__(self, db_path: str = "data/portfolio/portfolio.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(CREATE_TABLE_SQL)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def append_event(self, event: PortfolioEvent) -> None:
        """Insert an event into the store (idempotent by event_id)."""
        d = event.to_dict()
        payload = json.dumps(d, ensure_ascii=False)
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO portfolio_events "
                "(event_id, event_type, timestamp, payload) VALUES (?, ?, ?, ?)",
                (d["event_id"], d["event_type"], d["timestamp"], payload),
            )

    def get_all_events(self) -> List[Dict[str, Any]]:
        """Return all events ordered by insertion time, as dicts."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT payload FROM portfolio_events ORDER BY id ASC"
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def event_count(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) FROM portfolio_events").fetchone()
            return row[0]
