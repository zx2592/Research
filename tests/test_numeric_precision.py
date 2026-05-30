"""
Phase 5 金融数值精度测试 — Decimal replay / Guard 边界精度
"""
import os
import tempfile
import shutil

import pytest

from services.portfolio.ledger import PortfolioLedger
from services.portfolio.events import FillEvent, CashFlowEvent
from services.execution.guards import MaxPositionGuard
from core.artifacts.schemas import OrderIntent


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp(prefix="alpha_precision_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _ledger(tmp_dir):
    return PortfolioLedger(db_path=os.path.join(tmp_dir, "precision.db"))


class TestLedgerPrecision:
    def test_buy_sell_exact_zero(self, tmp_dir):
        """买100卖100后精确清零，无浮点幽灵持仓。"""
        ledger = _ledger(tmp_dir)
        ledger.emit(CashFlowEvent(amount=100000, category="deposit"))
        ledger.emit(FillEvent(
            ticker="AAPL", side="buy", quantity=100,
            price=150.0, commission=0, account="test",
        ))
        ledger.emit(FillEvent(
            ticker="AAPL", side="sell", quantity=100,
            price=155.0, commission=0, account="test",
        ))
        snapshot = ledger.current_snapshot()
        assert len(snapshot.positions) == 0
        # Cash should be exactly: 100000 - 15000 + 15500 = 100500
        assert snapshot.cash == pytest.approx(100500.0, abs=1e-9)

    def test_partial_sell_precision(self, tmp_dir):
        """买100卖33.33，剩余精确66.67。"""
        ledger = _ledger(tmp_dir)
        ledger.emit(CashFlowEvent(amount=100000, category="deposit"))
        ledger.emit(FillEvent(
            ticker="AAPL", side="buy", quantity=100,
            price=150.0, commission=0, account="test",
        ))
        ledger.emit(FillEvent(
            ticker="AAPL", side="sell", quantity=33.33,
            price=155.0, commission=0, account="test",
        ))
        snapshot = ledger.current_snapshot()
        pos = snapshot.get_position("AAPL")
        assert pos is not None
        assert pos.shares == pytest.approx(66.67, abs=1e-9)

    def test_cost_basis_weighted_avg(self, tmp_dir):
        """多次买入的加权平均成本精确。"""
        ledger = _ledger(tmp_dir)
        ledger.emit(CashFlowEvent(amount=100000, category="deposit"))
        # Buy 50 @ 100
        ledger.emit(FillEvent(
            ticker="TSLA", side="buy", quantity=50,
            price=100.0, commission=0, account="test",
        ))
        # Buy 50 @ 200
        ledger.emit(FillEvent(
            ticker="TSLA", side="buy", quantity=50,
            price=200.0, commission=0, account="test",
        ))
        snapshot = ledger.current_snapshot()
        pos = snapshot.get_position("TSLA")
        assert pos is not None
        assert pos.shares == pytest.approx(100.0, abs=1e-9)
        # avg_cost should be (50*100 + 50*200) / 100 = 150
        assert pos.avg_cost == pytest.approx(150.0, abs=1e-9)
        assert pos.cost_basis == pytest.approx(15000.0, abs=1e-9)

    def test_large_amount_no_drift(self, tmp_dir):
        """$10M+ 金额无精度丢失。"""
        ledger = _ledger(tmp_dir)
        ledger.emit(CashFlowEvent(amount=50_000_000, category="deposit"))
        ledger.emit(FillEvent(
            ticker="BRK.A", side="buy", quantity=100,
            price=499999.99, commission=10.01, account="test",
        ))
        snapshot = ledger.current_snapshot()
        pos = snapshot.get_position("BRK.A")
        assert pos is not None
        assert pos.shares == pytest.approx(100.0)
        # total_cost = 100 * 499999.99 + 10.01 = 49999999 + 10.01 = 50000009.01
        # But we actually get exactly that with Decimal
        expected_cost = 100 * 499999.99 + 10.01
        assert pos.cost_basis == pytest.approx(expected_cost, abs=0.01)

    def test_many_small_trades_no_accumulation(self, tmp_dir):
        """大量小额交易不累积浮点误差。"""
        ledger = _ledger(tmp_dir)
        ledger.emit(CashFlowEvent(amount=1_000_000, category="deposit"))
        # Buy 1 share 100 times
        for _ in range(100):
            ledger.emit(FillEvent(
                ticker="XYZ", side="buy", quantity=1,
                price=99.99, commission=0.01, account="test",
            ))
        snapshot = ledger.current_snapshot()
        pos = snapshot.get_position("XYZ")
        assert pos is not None
        assert pos.shares == pytest.approx(100.0, abs=1e-9)
        # total_cost = 100 * (99.99 + 0.01) = 100 * 100.00 = 10000
        assert pos.cost_basis == pytest.approx(10000.0, abs=1e-9)


class TestGuardBoundaryPrecision:
    def test_exact_boundary_pass(self, tmp_dir):
        """14.999...% 应该通过 15% 限制。"""
        ledger = _ledger(tmp_dir)
        ledger.emit(CashFlowEvent(amount=100000, category="deposit"))
        # Existing position: 50 shares @ 29.99 = $1499.50
        ledger.emit(FillEvent(
            ticker="TEST", side="buy", quantity=50,
            price=29.99, commission=0, account="test",
        ))
        guard = MaxPositionGuard(max_pct=15.0, ledger=ledger)
        # Portfolio NAV: 100000 (cash remaining after buy = 100000 - 1499.50 = 98500.50)
        # With prices: position value = 50 * 29.99 = 1499.50
        # total_nav = 98500.50 + 1499.50 = 100000
        # We want to buy more to get just under 15%
        # Target: projected_value / 100000 * 100 < 15%
        # 15% of 100000 = 15000
        # existing_value = 50 * 29.99 = 1499.50
        # order_value needs to be 15000 - 1499.50 - tiny = 13500.49
        # quantity at price 29.99 = 13500.49 / 29.99 ≈ 450.17
        # Let's try 449 shares → projected = 50*29.99 + 449*29.99 = 499*29.99 = 14965.01
        # 14965.01 / 100000 * 100 = 14.96501% → should pass
        intent = OrderIntent(
            ticker="TEST", side="buy", quantity=449,
            order_type="limit", limit_price=29.99, rationale="test", confidence=0.9,
        )
        result = guard.check(intent, {"TEST": 29.99})
        assert result.passed

    def test_exact_boundary_fail(self, tmp_dir):
        """15.001% 应该被 15% 限制拦截。"""
        ledger = _ledger(tmp_dir)
        ledger.emit(CashFlowEvent(amount=100000, category="deposit"))
        guard = MaxPositionGuard(max_pct=15.0, ledger=ledger)
        # Buy 501 shares @ 30 = 15030
        # 15030 / 100000 * 100 = 15.03% → should fail
        intent = OrderIntent(
            ticker="TEST", side="buy", quantity=501,
            order_type="limit", limit_price=30.0, rationale="test", confidence=0.9,
        )
        result = guard.check(intent, {"TEST": 30.0})
        assert not result.passed

    def test_boundary_exactly_at_limit(self, tmp_dir):
        """精确 15.0% 应该通过（>= 15 才拒绝？不, > max_pct 才拒绝）。"""
        ledger = _ledger(tmp_dir)
        ledger.emit(CashFlowEvent(amount=100000, category="deposit"))
        guard = MaxPositionGuard(max_pct=15.0, ledger=ledger)
        # Buy 500 shares @ 30 = 15000
        # 15000 / 100000 * 100 = 15.0% → exactly at max, condition is > so it passes
        intent = OrderIntent(
            ticker="TEST", side="buy", quantity=500,
            order_type="limit", limit_price=30.0, rationale="test", confidence=0.9,
        )
        result = guard.check(intent, {"TEST": 30.0})
        assert result.passed
