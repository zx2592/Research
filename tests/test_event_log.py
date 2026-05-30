"""
TDD Tests for core/event_log.py — EventLog (全局事件总线)

Tests written FIRST, implementation follows.
"""
import os
import json
import time
from datetime import datetime, timezone

import pytest

from core.event_log import Event, EventLog


# ── Event dataclass ──────────────────────────────────────────────

class TestEvent:
    def test_create_event_with_defaults(self):
        """Event should auto-generate event_id and timestamp."""
        e = Event(event_type="test.ping", source="unit_test", payload={"msg": "hello"})
        assert e.event_id  # non-empty UUID
        assert isinstance(e.timestamp, datetime)
        assert e.event_type == "test.ping"
        assert e.source == "unit_test"
        assert e.payload == {"msg": "hello"}

    def test_event_to_dict(self):
        """Event.to_dict() should produce a JSON-serializable dict."""
        e = Event(event_type="order.filled", source="execution", payload={"qty": 100})
        d = e.to_dict()
        assert d["event_type"] == "order.filled"
        assert d["source"] == "execution"
        assert d["payload"]["qty"] == 100
        # Confirm JSON-serializable
        json.dumps(d)

    def test_event_from_dict_roundtrip(self):
        """Event should survive to_dict → from_dict roundtrip."""
        original = Event(event_type="data.fetch", source="datahub", payload={"ticker": "NVDA"})
        restored = Event.from_dict(original.to_dict())
        assert restored.event_id == original.event_id
        assert restored.event_type == original.event_type
        assert restored.source == original.source
        assert restored.payload == original.payload


# ── EventLog core ────────────────────────────────────────────────

class TestEventLog:
    def test_emit_creates_file(self, tmp_dir):
        """First emit should create the JSONL file."""
        log = EventLog(log_dir=tmp_dir)
        e = Event(event_type="system.start", source="test", payload={})
        log.emit(e)
        assert os.path.exists(log.log_path)

    def test_emit_appends_events(self, tmp_dir):
        """Multiple emits should append lines."""
        log = EventLog(log_dir=tmp_dir)
        for i in range(5):
            log.emit(Event(event_type=f"test.{i}", source="test", payload={"i": i}))
        with open(log.log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 5

    def test_emit_is_valid_jsonl(self, tmp_dir):
        """Each line must be valid JSON."""
        log = EventLog(log_dir=tmp_dir)
        log.emit(Event(event_type="test.json", source="test", payload={"key": "value"}))
        with open(log.log_path, "r", encoding="utf-8") as f:
            for line in f:
                data = json.loads(line.strip())
                assert "event_id" in data
                assert "event_type" in data

    def test_query_by_event_type(self, tmp_dir):
        """query() should filter by event_type."""
        log = EventLog(log_dir=tmp_dir)
        log.emit(Event(event_type="order.staged", source="exec", payload={"a": 1}))
        log.emit(Event(event_type="data.fetch", source="hub", payload={"b": 2}))
        log.emit(Event(event_type="order.filled", source="exec", payload={"c": 3}))

        orders = log.query(event_type="order")
        assert len(orders) == 2
        assert all("order" in e.event_type for e in orders)

    def test_query_by_since(self, tmp_dir):
        """query(since=...) should only return events after that time."""
        log = EventLog(log_dir=tmp_dir)
        log.emit(Event(event_type="old.event", source="test", payload={}))

        # Read back the old event's timestamp, then use it as the since marker
        old_events = list(log.replay())
        after = old_events[0].timestamp  # query uses strict >, so old event is excluded

        time.sleep(0.02)
        log.emit(Event(event_type="new.event", source="test", payload={}))

        results = log.query(since=after)
        assert len(results) == 1
        assert results[0].event_type == "new.event"

    def test_query_by_source(self, tmp_dir):
        """query(source=...) should filter by source."""
        log = EventLog(log_dir=tmp_dir)
        log.emit(Event(event_type="a", source="datahub", payload={}))
        log.emit(Event(event_type="b", source="execution", payload={}))
        log.emit(Event(event_type="c", source="datahub", payload={}))

        results = log.query(source="datahub")
        assert len(results) == 2

    def test_replay_returns_all_in_order(self, tmp_dir):
        """replay() should yield all events in chronological order."""
        log = EventLog(log_dir=tmp_dir)
        for i in range(10):
            log.emit(Event(event_type=f"seq.{i}", source="test", payload={"seq": i}))

        events = list(log.replay())
        assert len(events) == 10
        for i, e in enumerate(events):
            assert e.payload["seq"] == i

    def test_count(self, tmp_dir):
        """count() should return total number of events."""
        log = EventLog(log_dir=tmp_dir)
        assert log.count() == 0
        for i in range(7):
            log.emit(Event(event_type="x", source="test", payload={}))
        assert log.count() == 7

    def test_empty_log_query(self, tmp_dir):
        """Querying an empty / nonexistent log should return []."""
        log = EventLog(log_dir=tmp_dir)
        assert log.query(event_type="anything") == []
        assert list(log.replay()) == []

    def test_crash_recovery_partial_line(self, tmp_dir):
        """If last line is incomplete (crash), it should be skipped gracefully."""
        log = EventLog(log_dir=tmp_dir)
        log.emit(Event(event_type="good", source="test", payload={"ok": True}))
        # Simulate crash: append partial JSON
        with open(log.log_path, "a", encoding="utf-8") as f:
            f.write('{"event_id": "broken", "event_type": "bad"')  # no closing brace, no newline

        events = list(log.replay())
        assert len(events) == 1
        assert events[0].event_type == "good"

    def test_unicode_payload(self, tmp_dir):
        """Should handle CJK and emoji in payload."""
        log = EventLog(log_dir=tmp_dir)
        log.emit(Event(event_type="test.unicode", source="test",
                        payload={"msg": "买入 NVDA 🚀", "ticker": "腾讯"}))
        events = list(log.replay())
        assert events[0].payload["msg"] == "买入 NVDA 🚀"
        assert events[0].payload["ticker"] == "腾讯"
