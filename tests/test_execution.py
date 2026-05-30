"""
TDD Tests for services/execution/ — ExecutionGateway

Tests written FIRST. Covers:
- OrderIntent: schema, status lifecycle
- Guards: individual guards + guard chain
- Pipeline: stage → commit → guard → push → settle (Paper mode)
- Wallet: commit history JSONL
- KillSwitch: emergency stop
"""
import os
import json
import pytest

from core.artifacts.schemas import OrderIntent
from services.execution.guards import (
    MaxPositionGuard, CooldownGuard, GuardChain, GuardResult
)
from services.execution.pipeline import ExecutionPipeline, PipelineError
from services.execution.wallet import Wallet
from services.execution.kill_switch import KillSwitch
from services.execution.adapters.paper import PaperAdapter
from services.portfolio.ledger import PortfolioLedger
from services.portfolio.events import CashFlowEvent


# ── Guards ───────────────────────────────────────────────────────

class TestMaxPositionGuard:
    def test_new_position_below_limit_passes(self, tmp_dir):
        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        ledger.emit(CashFlowEvent(1_000_000.0, "USD", "deposit"))
        guard = MaxPositionGuard(max_pct=20.0, ledger=ledger)
        # Buy $100k of a ticker in a $1M portfolio = 10% → pass
        intent = OrderIntent(
            ticker="NVDA", side="buy", quantity=1000,
            order_type="market", rationale="test", confidence=0.8,
        )
        result = guard.check(intent, {"NVDA": 100.0})
        assert result.passed

    def test_position_over_limit_fails(self, tmp_dir):
        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        ledger.emit(CashFlowEvent(1_000_000.0, "USD", "deposit"))
        guard = MaxPositionGuard(max_pct=10.0, ledger=ledger)
        # Buy $500k of a ticker in a $1M portfolio = 50% → fail
        intent = OrderIntent(
            ticker="NVDA", side="buy", quantity=5000,
            order_type="market", rationale="test", confidence=0.8,
        )
        result = guard.check(intent, {"NVDA": 100.0})
        assert not result.passed
        assert result.reason


class TestGuardChain:
    def test_empty_chain_passes(self):
        chain = GuardChain(guards=[])
        intent = OrderIntent(
            ticker="GOOG", side="buy", quantity=10,
            order_type="market", rationale="ok", confidence=0.7,
        )
        result = chain.run(intent, {})
        assert result.passed

    def test_chain_with_failing_guard(self, tmp_dir):
        """If any guard fails, the chain fails."""
        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        ledger.emit(CashFlowEvent(100_000.0, "USD", "deposit"))
        chain = GuardChain(guards=[
            MaxPositionGuard(max_pct=5.0, ledger=ledger),  # very strict
        ])
        intent = OrderIntent(
            ticker="GOOG", side="buy", quantity=100,
            order_type="market", rationale="test", confidence=0.7,
        )
        result = chain.run(intent, {"GOOG": 170.0})  # $17k in $100k = 17% → fail
        assert not result.passed

    def test_chain_all_pass(self, tmp_dir):
        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        ledger.emit(CashFlowEvent(1_000_000.0, "USD", "deposit"))
        chain = GuardChain(guards=[
            MaxPositionGuard(max_pct=50.0, ledger=ledger),
        ])
        intent = OrderIntent(
            ticker="GOOG", side="buy", quantity=10,
            order_type="market", rationale="ok", confidence=0.9,
        )
        result = chain.run(intent, {"GOOG": 170.0})  # $1700 in $1M → pass
        assert result.passed


# ── Wallet ───────────────────────────────────────────────────────

class TestWallet:
    def test_commit_writes_to_jsonl(self, tmp_dir):
        wallet = Wallet(history_path=os.path.join(tmp_dir, "wallet.jsonl"))
        intent = OrderIntent(
            ticker="NVDA", side="buy", quantity=100,
            order_type="market", rationale="dip buy", confidence=0.8,
        )
        commit_hash = wallet.commit(intent, message="Buy the dip")
        assert len(commit_hash) == 8  # 8-char hash
        assert os.path.exists(wallet.history_path)

    def test_commit_is_readable(self, tmp_dir):
        wallet = Wallet(history_path=os.path.join(tmp_dir, "wallet.jsonl"))
        intent = OrderIntent(
            ticker="GOOG", side="sell", quantity=50,
            order_type="limit", limit_price=180.0,
            rationale="target hit", confidence=0.9,
        )
        wallet.commit(intent, "Target reached")
        history = wallet.get_history()
        assert len(history) == 1
        assert history[0]["ticker"] == "GOOG"

    def test_multiple_commits(self, tmp_dir):
        wallet = Wallet(history_path=os.path.join(tmp_dir, "wallet.jsonl"))
        for i in range(5):
            intent = OrderIntent(
                ticker=f"TICK{i}", side="buy", quantity=100.0,
                order_type="market", rationale=f"reason {i}", confidence=0.7,
            )
            wallet.commit(intent, f"commit {i}")
        assert len(wallet.get_history()) == 5


# ── KillSwitch ───────────────────────────────────────────────────

class TestKillSwitch:
    def test_initially_inactive(self, tmp_dir):
        ks = KillSwitch(state_path=os.path.join(tmp_dir, "ks.json"))
        assert not ks.is_active()

    def test_activate_blocks_trading(self, tmp_dir):
        ks = KillSwitch(state_path=os.path.join(tmp_dir, "ks.json"))
        ks.activate(reason="Test emergency stop")
        assert ks.is_active()

    def test_deactivate_allows_trading(self, tmp_dir):
        ks = KillSwitch(state_path=os.path.join(tmp_dir, "ks.json"))
        ks.activate("test")
        ks.deactivate()
        assert not ks.is_active()

    def test_state_persists_across_instances(self, tmp_dir):
        path = os.path.join(tmp_dir, "ks.json")
        ks1 = KillSwitch(state_path=path)
        ks1.activate("emergency")
        ks2 = KillSwitch(state_path=path)
        assert ks2.is_active()


# ── ExecutionPipeline (Paper mode) ───────────────────────────────

class TestExecutionPipeline:
    def _make_pipeline(self, tmp_dir):
        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        ledger.emit(CashFlowEvent(1_000_000.0, "USD", "deposit"))
        wallet = Wallet(history_path=os.path.join(tmp_dir, "wallet.jsonl"))
        kill_switch = KillSwitch(state_path=os.path.join(tmp_dir, "ks.json"))
        guard_chain = GuardChain(guards=[
            MaxPositionGuard(max_pct=30.0, ledger=ledger),
        ])
        adapter = PaperAdapter(ledger=ledger)
        return ExecutionPipeline(
            ledger=ledger,
            wallet=wallet,
            guard_chain=guard_chain,
            adapter=adapter,
            kill_switch=kill_switch,
        )

    def test_paper_execute_success(self, tmp_dir):
        pipeline = self._make_pipeline(tmp_dir)
        intent = OrderIntent(
            ticker="NVDA", side="buy", quantity=100,
            order_type="market", rationale="test buy", confidence=0.8,
        )
        fill = pipeline.execute(intent, prices={"NVDA": 130.0})
        assert fill["ticker"] == "NVDA"
        assert fill["status"] == "filled"

    def test_guard_block_prevents_fill(self, tmp_dir):
        pipeline = self._make_pipeline(tmp_dir)
        # Try to buy 5000 shares @ $130 = $650k in $1M (65%) → exceeds 30% limit
        intent = OrderIntent(
            ticker="NVDA", side="buy", quantity=5000,
            order_type="market", rationale="too big", confidence=0.8,
        )
        with pytest.raises(PipelineError, match="Guard"):
            pipeline.execute(intent, prices={"NVDA": 130.0})

    def test_kill_switch_blocks_execution(self, tmp_dir):
        pipeline = self._make_pipeline(tmp_dir)
        pipeline.kill_switch.activate("emergency drill")
        intent = OrderIntent(
            ticker="GOOG", side="buy", quantity=10,
            order_type="market", rationale="ok", confidence=0.9,
        )
        with pytest.raises(PipelineError, match="KillSwitch"):
            pipeline.execute(intent, prices={"GOOG": 170.0})

    def test_fill_updates_ledger(self, tmp_dir):
        pipeline = self._make_pipeline(tmp_dir)
        intent = OrderIntent(
            ticker="SPOT", side="buy", quantity=50,
            order_type="market", rationale="add core", confidence=0.85,
        )
        pipeline.execute(intent, prices={"SPOT": 500.0})
        snapshot = pipeline.ledger.current_snapshot()
        spot = snapshot.get_position("SPOT")
        assert spot is not None
        assert spot.shares == 50.0

    def test_wallet_records_commit(self, tmp_dir):
        pipeline = self._make_pipeline(tmp_dir)
        intent = OrderIntent(
            ticker="V", side="buy", quantity=20,
            order_type="market", rationale="add core", confidence=0.9,
        )
        pipeline.execute(intent, prices={"V": 340.0})
        history = pipeline.wallet.get_history()
        assert len(history) == 1
        assert history[0]["ticker"] == "V"


# ── ReverseCooldownGuard ──────────────────────────────────────────

class TestReverseCooldownGuard:
    """
    Rule: after a SELL, cannot BUY the same ticker within cooldown_days.
    Default: 30 days.
    """

    def test_buy_after_sell_within_30d_blocked(self, tmp_dir):
        """Sell today → cannot buy same ticker within 30 days."""
        from services.execution.guards import ReverseCooldownGuard
        from services.portfolio.events import FillEvent
        from datetime import datetime, timezone, timedelta

        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        ledger.emit(CashFlowEvent(1_000_000.0, "USD", "deposit"))

        # Simulate a sell that happened 5 days ago
        sell = FillEvent(ticker="NVDA", side="sell", quantity=100,
                         price=130.0, commission=1.0, account="IB")
        sell.timestamp = datetime.now(timezone.utc) - timedelta(days=5)
        ledger.emit(sell)

        guard = ReverseCooldownGuard(cooldown_days=30, ledger=ledger)
        buy_intent = OrderIntent(
            ticker="NVDA", side="buy", quantity=50,
            order_type="market", rationale="dip buy", confidence=0.8,
        )
        result = guard.check(buy_intent, {})
        assert not result.passed
        assert "30" in result.reason or "day" in result.reason.lower()

    def test_buy_after_sell_after_30d_passes(self, tmp_dir):
        """Sell 31 days ago → can buy again."""
        from services.execution.guards import ReverseCooldownGuard
        from services.portfolio.events import FillEvent
        from datetime import datetime, timezone, timedelta

        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        ledger.emit(CashFlowEvent(1_000_000.0, "USD", "deposit"))

        sell = FillEvent(ticker="NVDA", side="sell", quantity=100,
                         price=130.0, commission=1.0, account="IB")
        sell.timestamp = datetime.now(timezone.utc) - timedelta(days=31)
        ledger.emit(sell)

        guard = ReverseCooldownGuard(cooldown_days=30, ledger=ledger)
        buy_intent = OrderIntent(
            ticker="NVDA", side="buy", quantity=50,
            order_type="market", rationale="re-enter", confidence=0.8,
        )
        result = guard.check(buy_intent, {})
        assert result.passed

    def test_sell_after_sell_not_blocked(self, tmp_dir):
        """Rule only applies to BUY after SELL — not SELL after SELL."""
        from services.execution.guards import ReverseCooldownGuard
        from services.portfolio.events import FillEvent
        from datetime import datetime, timezone, timedelta

        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        ledger.emit(CashFlowEvent(1_000_000.0, "USD", "deposit"))

        sell = FillEvent(ticker="NVDA", side="sell", quantity=100,
                         price=130.0, commission=1.0, account="IB")
        sell.timestamp = datetime.now(timezone.utc) - timedelta(days=1)
        ledger.emit(sell)

        guard = ReverseCooldownGuard(cooldown_days=30, ledger=ledger)
        sell_more = OrderIntent(
            ticker="NVDA", side="sell", quantity=50,
            order_type="market", rationale="more trim", confidence=0.8,
        )
        result = guard.check(sell_more, {})
        assert result.passed  # sell-after-sell is allowed

    def test_different_ticker_not_blocked(self, tmp_dir):
        """Sell NVDA → can still buy GOOG."""
        from services.execution.guards import ReverseCooldownGuard
        from services.portfolio.events import FillEvent
        from datetime import datetime, timezone, timedelta

        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        ledger.emit(CashFlowEvent(1_000_000.0, "USD", "deposit"))

        sell = FillEvent(ticker="NVDA", side="sell", quantity=100,
                         price=130.0, commission=1.0, account="IB")
        sell.timestamp = datetime.now(timezone.utc) - timedelta(days=1)
        ledger.emit(sell)

        guard = ReverseCooldownGuard(cooldown_days=30, ledger=ledger)
        buy_goog = OrderIntent(
            ticker="GOOG", side="buy", quantity=10,
            order_type="market", rationale="add position", confidence=0.9,
        )
        result = guard.check(buy_goog, {})
        assert result.passed

    def test_in_guard_chain(self, tmp_dir):
        """ReverseCooldownGuard integrates into GuardChain properly."""
        from services.execution.guards import ReverseCooldownGuard
        from services.portfolio.events import FillEvent
        from datetime import datetime, timezone, timedelta

        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        ledger.emit(CashFlowEvent(1_000_000.0, "USD", "deposit"))

        sell = FillEvent(ticker="GOOG", side="sell", quantity=20,
                         price=175.0, commission=1.0, account="IB")
        sell.timestamp = datetime.now(timezone.utc) - timedelta(days=3)
        ledger.emit(sell)

        chain = GuardChain(guards=[
            MaxPositionGuard(max_pct=30.0, ledger=ledger),
            ReverseCooldownGuard(cooldown_days=30, ledger=ledger),
        ])
        buy_intent = OrderIntent(
            ticker="GOOG", side="buy", quantity=5,
            order_type="market", rationale="re-enter", confidence=0.7,
        )
        result = chain.run(buy_intent, {"GOOG": 175.0})
        assert not result.passed  # blocked by ReverseCooldownGuard

