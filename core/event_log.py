"""
EventLog — 全局事件总线 (Global Event Bus)

Append-only JSONL event log with crash recovery.
Inspired by OpenAlice's EventLog design.

Usage:
    from core.event_log import Event, EventLog

    log = EventLog(log_dir="data/event_log")
    log.emit(Event(event_type="workflow.start", source="orchestrator", payload={...}))
    events = log.query(event_type="order", since=some_datetime)
"""

import os
import json
import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """A single event in the system."""
    event_type: str
    source: str
    payload: Dict[str, Any]
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "source": self.source,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Event":
        """Deserialize from a dict."""
        ts = d["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return cls(
            event_id=d["event_id"],
            timestamp=ts,
            event_type=d["event_type"],
            source=d["source"],
            payload=d.get("payload", {}),
        )


class EventLog:
    """
    Append-only JSONL event log.

    - emit(): append an event
    - query(): filter events by type, source, time
    - replay(): iterate all events in order
    - count(): total events
    - Crash-safe: skips malformed lines on read
    """

    def __init__(self, log_dir: str = "data/event_log", filename: str = "events.jsonl"):
        self.log_dir = log_dir
        self.log_path = os.path.join(log_dir, filename)

    def emit(self, event: Event) -> None:
        """Append an event to the log file."""
        os.makedirs(self.log_dir, exist_ok=True)
        line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line)

    def _read_events(self) -> List[Event]:
        """Read all events from the log file, skipping malformed lines."""
        if not os.path.exists(self.log_path):
            return []
        events = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    events.append(Event.from_dict(d))
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Skipping malformed line {line_num}: {e}")
        return events

    def query(
        self,
        event_type: Optional[str] = None,
        source: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> List[Event]:
        """
        Query events with optional filters.

        Args:
            event_type: substring match on event_type (e.g. "order" matches "order.staged")
            source: exact match on source
            since: only events after this timestamp
        """
        events = self._read_events()
        results = []
        for e in events:
            if event_type and event_type not in e.event_type:
                continue
            if source and e.source != source:
                continue
            if since and e.timestamp <= since:
                continue
            results.append(e)
        return results

    def replay(self, since: Optional[datetime] = None) -> Iterator[Event]:
        """Yield all events in chronological order, optionally since a given time."""
        events = self._read_events()
        for e in events:
            if since and e.timestamp <= since:
                continue
            yield e

    def count(self) -> int:
        """Return total number of valid events in the log."""
        return len(self._read_events())
