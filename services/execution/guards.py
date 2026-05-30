"""
Guards — 交易前硬风控检查链

Each guard is an independent check. The GuardChain runs them all.
If ANY guard fails, the trade is blocked before reaching the broker.

Guards implemented:
- MaxPositionGuard: single position weight limit
- CooldownGuard: minimum time between trades on same ticker
- ReverseCooldownGuard: after a SELL, blocks BUY of same ticker for N days (default 30)
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from core.artifacts.schemas import OrderIntent
from core import settings
from services.portfolio.ledger import PortfolioLedger


def _d(val) -> Decimal:
    """Convert to Decimal via string."""
    return Decimal(str(val))


@dataclass
class GuardResult:
    passed: bool
    reason: str = ""

    @classmethod
    def ok(cls) -> "GuardResult":
        return cls(passed=True)

    @classmethod
    def fail(cls, reason: str) -> "GuardResult":
        return cls(passed=False, reason=reason)


class MaxPositionGuard:
    """Block if the order would push a single position above max_pct% of NAV."""

    def __init__(self, max_pct: float = None, ledger: Optional[PortfolioLedger] = None):
        self.max_pct = max_pct if max_pct is not None else settings.execution.max_position_pct
        self.ledger = ledger

    def check(self, intent: OrderIntent, prices: Dict[str, float]) -> GuardResult:
        if self.ledger is None:
            return GuardResult.ok()

        snapshot = self.ledger.current_snapshot(prices=prices)

        total_nav = snapshot.total_nav
        if total_nav is None or total_nav <= 0:
            cost_total = sum(p.cost_basis for p in snapshot.positions)
            total_nav = cost_total + snapshot.cash

        if total_nav <= 0:
            return GuardResult.ok()

        # Use Decimal for precise boundary calculations
        d_total_nav = _d(total_nav)

        existing = snapshot.get_position(intent.ticker)
        d_existing_value = Decimal("0")
        if existing:
            price = prices.get(intent.ticker, existing.avg_cost)
            d_existing_value = _d(existing.shares) * _d(price)

        d_price = _d(prices.get(intent.ticker, 0.0))
        d_order_value = _d(intent.quantity) * d_price

        d_projected_value = d_existing_value + (d_order_value if intent.side == "buy" else -d_order_value)
        d_projected_pct = (d_projected_value / d_total_nav) * Decimal("100")
        projected_pct = float(d_projected_pct)

        if projected_pct > self.max_pct:
            return GuardResult.fail(
                f"{intent.ticker} projected to {projected_pct:.1f}% of NAV "
                f"(max {self.max_pct}%)"
            )
        return GuardResult.ok()


class CooldownGuard:
    """Block if same ticker was traded within cooldown_hours."""

    def __init__(self, cooldown_hours: float = None, ledger: Optional[PortfolioLedger] = None):
        self.cooldown_hours = cooldown_hours if cooldown_hours is not None else settings.execution.cooldown_hours
        self.ledger = ledger

    def check(self, intent: OrderIntent, prices: Dict[str, float]) -> GuardResult:
        if self.ledger is None:
            return GuardResult.ok()

        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.cooldown_hours)
        raw_events = self.ledger.db.get_all_events()

        for ev in raw_events:
            if ev.get("event_type") != "fill":
                continue
            if ev.get("ticker") != intent.ticker:
                continue
            ts_str = ev.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    return GuardResult.fail(
                        f"Cooldown: {intent.ticker} traded within {self.cooldown_hours}h "
                        f"(last at {ts.isoformat()})"
                    )
            except ValueError:
                continue

        return GuardResult.ok()


class ReverseCooldownGuard:
    """
    反向交易冷却 — 卖出后 N 天内禁止买回同一标的。

    Rule: if the most recent SELL of `intent.ticker` was within
    `cooldown_days`, block any BUY order for that ticker.

    Only triggers on BUY orders (sell-after-sell is not restricted).
    Default: 30 days.
    """

    def __init__(
        self,
        cooldown_days: int = None,
        ledger: Optional[PortfolioLedger] = None,
    ):
        self.cooldown_days = cooldown_days if cooldown_days is not None else settings.execution.reverse_cooldown_days
        self.ledger = ledger

    def check(self, intent: OrderIntent, prices: Dict[str, float]) -> GuardResult:
        # Only applies to BUY orders
        if intent.side != "buy":
            return GuardResult.ok()

        if self.ledger is None:
            return GuardResult.ok()

        cutoff = datetime.now(timezone.utc) - timedelta(days=self.cooldown_days)
        raw_events = self.ledger.db.get_all_events()

        # Find the most recent SELL for this ticker
        most_recent_sell: Optional[datetime] = None
        for ev in raw_events:
            if ev.get("event_type") != "fill":
                continue
            if ev.get("ticker") != intent.ticker:
                continue
            if ev.get("side") != "sell":
                continue
            ts_str = ev.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if most_recent_sell is None or ts > most_recent_sell:
                    most_recent_sell = ts
            except ValueError:
                continue

        if most_recent_sell is None:
            return GuardResult.ok()  # Never sold → no restriction

        if most_recent_sell >= cutoff:
            days_since = (datetime.now(timezone.utc) - most_recent_sell).days
            days_remaining = self.cooldown_days - days_since
            return GuardResult.fail(
                f"反向交易冷却: {intent.ticker} 卖出后须等待 {self.cooldown_days} 天方可买回 "
                f"（距上次卖出 {days_since} 天，还需等待 {days_remaining} 天）"
            )

        return GuardResult.ok()


class GuardChain:
    """Runs a sequence of guards. Fails fast on first failure."""

    def __init__(self, guards: List):
        self.guards = guards

    def run(self, intent: OrderIntent, prices: Dict[str, float]) -> GuardResult:
        for guard in self.guards:
            result = guard.check(intent, prices)
            if not result.passed:
                return result
        return GuardResult.ok()
