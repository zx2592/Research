"""
TDD Tests for services/portfolio/ — PortfolioLedger

Tests written FIRST. Covers:
- PortfolioEvent / FillEvent / CashFlowEvent data models
- SQLite storage layer (db.py)
- PortfolioLedger core (event sourcing: emit, replay, snapshot)
- PortfolioHealth checks (concentration, leverage, cash %)
- CSV importer (from holdings.json genesis import)
"""
import os
import json
import sqlite3
from datetime import datetime, timezone, date
from typing import List

import pytest

from services.portfolio.events import FillEvent, CashFlowEvent, EventType
from services.portfolio.db import PortfolioDatabase
from services.portfolio.ledger import PortfolioLedger
from services.portfolio.snapshot import PortfolioSnapshot, PositionState
from services.portfolio.health import HealthChecker, HealthReport


# ── Event Models ─────────────────────────────────────────────────

class TestPortfolioEvents:
    def test_fill_event_creation(self):
        e = FillEvent(
            ticker="NVDA",
            side="buy",
            quantity=100.0,
            price=130.0,
            commission=1.0,
            account="U123",
        )
        assert e.event_type == EventType.FILL
        assert e.ticker == "NVDA"
        assert e.quantity == 100.0
        assert e.event_id  # auto-generated

    def test_cash_flow_event_creation(self):
        e = CashFlowEvent(
            amount=10000.0,
            currency="USD",
            category="deposit",
        )
        assert e.event_type == EventType.CASH_FLOW
        assert e.amount == 10000.0

    def test_fill_event_to_dict_roundtrip(self):
        e = FillEvent(
            ticker="GOOG",
            side="sell",
            quantity=50.0,
            price=170.0,
            commission=0.5,
            account="U456",
        )
        d = e.to_dict()
        assert d["ticker"] == "GOOG"
        assert d["side"] == "sell"
        json.dumps(d)  # must be serializable


# ── SQLite Database ───────────────────────────────────────────────

class TestPortfolioDatabase:
    def test_create_database(self, tmp_dir):
        db = PortfolioDatabase(os.path.join(tmp_dir, "test.db"))
        assert os.path.exists(db.db_path)

    def test_insert_and_retrieve_fill(self, tmp_dir):
        db = PortfolioDatabase(os.path.join(tmp_dir, "p.db"))
        e = FillEvent(
            ticker="NVDA", side="buy", quantity=100.0,
            price=130.0, commission=1.0, account="U1",
        )
        db.append_event(e)
        events = db.get_all_events()
        assert len(events) == 1
        assert events[0]["ticker"] == "NVDA"

    def test_insert_multiple_events(self, tmp_dir):
        db = PortfolioDatabase(os.path.join(tmp_dir, "p.db"))
        for i in range(5):
            db.append_event(FillEvent(
                ticker=f"TICK{i}", side="buy", quantity=float(i+1),
                price=100.0, commission=1.0, account="U1",
            ))
        events = db.get_all_events()
        assert len(events) == 5

    def test_events_ordered_by_timestamp(self, tmp_dir):
        db = PortfolioDatabase(os.path.join(tmp_dir, "p.db"))
        for i in range(3):
            db.append_event(FillEvent(
                ticker="X", side="buy", quantity=float(i+1),
                price=100.0, commission=0.0, account="U1",
            ))
        events = db.get_all_events()
        # Quantities should be 1, 2, 3 in order
        quantities = [e["quantity"] for e in events if e.get("ticker") == "X"]
        assert quantities == [1.0, 2.0, 3.0]


# ── PortfolioLedger (Core) ────────────────────────────────────────

class TestPortfolioLedger:
    def test_emit_and_count_events(self, tmp_dir):
        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        ledger.emit(FillEvent("NVDA", "buy", 100.0, 130.0, 1.0, "U1"))
        ledger.emit(FillEvent("GOOG", "buy", 50.0, 170.0, 0.5, "U1"))
        assert ledger.event_count() == 2

    def test_buy_increases_position(self, tmp_dir):
        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        ledger.emit(CashFlowEvent(1_000_000.0, "USD", "deposit"))
        ledger.emit(FillEvent("NVDA", "buy", 100.0, 130.0, 0.0, "U1"))
        snapshot = ledger.current_snapshot()
        nvda = snapshot.get_position("NVDA")
        assert nvda is not None
        assert nvda.shares == 100.0

    def test_sell_decreases_position(self, tmp_dir):
        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        ledger.emit(CashFlowEvent(1_000_000.0, "USD", "deposit"))
        ledger.emit(FillEvent("NVDA", "buy", 100.0, 130.0, 0.0, "U1"))
        ledger.emit(FillEvent("NVDA", "sell", 40.0, 140.0, 0.0, "U1"))
        snapshot = ledger.current_snapshot()
        nvda = snapshot.get_position("NVDA")
        assert nvda.shares == 60.0

    def test_sell_all_removes_position(self, tmp_dir):
        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        ledger.emit(CashFlowEvent(500_000.0, "USD", "deposit"))
        ledger.emit(FillEvent("NVDA", "buy", 100.0, 130.0, 0.0, "U1"))
        ledger.emit(FillEvent("NVDA", "sell", 100.0, 140.0, 0.0, "U1"))
        snapshot = ledger.current_snapshot()
        # Position closed — should not appear in active positions
        assert snapshot.get_position("NVDA") is None

    def test_cash_tracking(self, tmp_dir):
        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        ledger.emit(CashFlowEvent(500_000.0, "USD", "deposit"))
        ledger.emit(FillEvent("NVDA", "buy", 100.0, 130.0, 0.0, "U1"))
        snapshot = ledger.current_snapshot()
        # After buying 100 at $130, cash should be 500000 - 13000 = 487000
        assert abs(snapshot.cash - 487_000.0) < 0.01

    def test_replay_from_zero(self, tmp_dir):
        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        ledger.emit(CashFlowEvent(1_000_000.0, "USD", "deposit"))
        ledger.emit(FillEvent("NVDA", "buy", 100.0, 130.0, 1.0, "U1"))
        ledger.emit(FillEvent("GOOG", "buy", 50.0, 170.0, 0.5, "U1"))
        ledger.emit(FillEvent("NVDA", "sell", 30.0, 140.0, 0.0, "U1"))
        # Replay should produce the same snapshot
        snapshot = ledger.replay()
        nvda = snapshot.get_position("NVDA")
        assert nvda.shares == 70.0

    def test_multiple_tickers(self, tmp_dir):
        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        ledger.emit(CashFlowEvent(5_000_000.0, "USD", "deposit"))
        tickers = ["NVDA", "GOOG", "SPOT", "V", "MA"]
        for t in tickers:
            ledger.emit(FillEvent(t, "buy", 100.0, 100.0, 0.0, "U1"))
        snapshot = ledger.current_snapshot()
        assert len(snapshot.positions) == 5


# ── PortfolioHealth ───────────────────────────────────────────────

class TestHealthChecker:
    def _make_snapshot(self, tmp_dir) -> PortfolioSnapshot:
        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        ledger.emit(CashFlowEvent(1_000_000.0, "USD", "deposit"))
        # Concentrated: 50% in NVDA
        ledger.emit(FillEvent("NVDA", "buy", 1000.0, 500.0, 0.0, "U1"))  # $500k
        ledger.emit(FillEvent("GOOG", "buy", 1000.0, 170.0, 0.0, "U1"))  # $170k
        return ledger.current_snapshot(prices={"NVDA": 500.0, "GOOG": 170.0})

    def test_concentration_flag(self, tmp_dir):
        snapshot = self._make_snapshot(tmp_dir)
        checker = HealthChecker(max_single_position_pct=25.0)
        report = checker.check(snapshot)
        # NVDA at $500k out of ~$830k equity = ~60% — should flag
        assert report.has_concentration_warning

    def test_cash_pct(self, tmp_dir):
        snapshot = self._make_snapshot(tmp_dir)
        checker = HealthChecker()
        report = checker.check(snapshot)
        # Cash = 1M - 500k - 170k = 330k; total = ~1M; cash% ≈ 33%
        assert report.cash_pct > 0

    def test_report_serializable(self, tmp_dir):
        snapshot = self._make_snapshot(tmp_dir)
        checker = HealthChecker()
        report = checker.check(snapshot)
        d = report.to_dict()
        json.dumps(d)


# ── CSV Importer (Genesis Import from holdings.json) ─────────────

class TestCSVImporter:
    def test_genesis_import_from_holdings_json(self, tmp_dir):
        """Import from the existing holdings.json to seed the Ledger."""
        from services.portfolio.importers.csv_importer import HoldingsImporter
        holdings_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "Config", "holdings.json"
        )
        if not os.path.exists(holdings_path):
            pytest.skip("Config/holdings.json not found")

        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        importer = HoldingsImporter()
        events = importer.import_from_holdings_json(holdings_path)
        for e in events:
            ledger.emit(e)

        snapshot = ledger.current_snapshot()
        # Should have positions and cash
        assert len(snapshot.positions) > 0
        assert snapshot.cash >= 0
