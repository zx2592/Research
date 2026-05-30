"""
PortfolioLedger — 组合账本（Event Sourcing 核心）

Single source of truth for all portfolio positions.
Every position change comes from an event.
Supports full replay from zero to reconstruct any state.
Uses Decimal internally for precise financial calculations.
"""
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from services.portfolio.events import (
    CashFlowEvent, EventType, FillEvent, PortfolioEvent, SplitEvent
)
from services.portfolio.db import PortfolioDatabase
from services.portfolio.snapshot import PortfolioSnapshot, PositionState


def _d(val) -> Decimal:
    """Convert to Decimal via string to avoid float precision loss."""
    return Decimal(str(val))


class PortfolioLedger:
    """
    Event-sourced portfolio ledger.

    - emit(): record a new event
    - current_snapshot(): compute current state
    - replay(): recompute from all events (full audit trail)
    - event_count(): total events stored
    """

    def __init__(self, db_path: str = "data/portfolio/portfolio.db"):
        self.db = PortfolioDatabase(db_path)

    def emit(self, event: PortfolioEvent) -> None:
        """Record a new portfolio event."""
        self.db.append_event(event)

    def event_count(self) -> int:
        """Total number of events in the ledger."""
        return self.db.event_count()

    def current_snapshot(self, prices: Optional[Dict[str, float]] = None) -> PortfolioSnapshot:
        """Compute the current portfolio state by replaying all events."""
        return self.replay(prices=prices)

    def replay(
        self,
        up_to: Optional[datetime] = None,
        prices: Optional[Dict[str, float]] = None,
    ) -> PortfolioSnapshot:
        """
        Replay all events (optionally up to a timestamp) to produce a snapshot.

        This is the canonical way to compute portfolio state.
        Uses Decimal arithmetic internally for precision.
        """
        raw_events = self.db.get_all_events()

        cash = Decimal("0")
        # ticker -> {shares: Decimal, total_cost: Decimal}
        positions: Dict[str, Dict] = {}

        for ev in raw_events:
            # Honour the up_to filter
            if up_to:
                ts = datetime.fromisoformat(ev["timestamp"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts > up_to:
                    break

            etype = ev["event_type"]

            if etype == EventType.FILL.value:
                ticker = ev["ticker"]
                qty = _d(ev.get("quantity", 0))
                price = _d(ev.get("price", 0))
                commission = _d(ev.get("commission", 0))

                if ev["side"] == "buy":
                    cost = qty * price + commission
                    cash -= cost
                    if ticker not in positions:
                        positions[ticker] = {"shares": Decimal("0"), "total_cost": Decimal("0")}
                    positions[ticker]["shares"] += qty
                    positions[ticker]["total_cost"] += cost

                elif ev["side"] == "sell":
                    proceeds = qty * price - commission
                    cash += proceeds
                    if ticker in positions:
                        # Reduce shares; scale cost basis proportionally
                        pos = positions[ticker]
                        old_shares = pos["shares"]
                        if old_shares > 0:
                            cost_per_share = pos["total_cost"] / old_shares
                            pos["total_cost"] -= cost_per_share * qty
                        pos["shares"] -= qty
                        if pos["shares"] <= 0:
                            del positions[ticker]

            elif etype == EventType.CASH_FLOW.value:
                amount = _d(ev.get("amount", 0))
                category = ev.get("category", "deposit")
                if category in ("deposit", "dividend", "interest", "option_premium"):
                    cash += amount
                elif category == "withdrawal":
                    cash -= amount

            elif etype == EventType.SPLIT.value:
                ticker = ev.get("ticker", "")
                ratio = _d(ev.get("ratio", 1.0))
                if ticker in positions:
                    positions[ticker]["shares"] *= ratio
                    # Cost basis per share adjusts inverse to ratio
                    # total_cost stays the same

        # Build PositionState objects (convert back to float for external API)
        position_states = []
        for ticker, data in positions.items():
            shares = float(data["shares"])
            total_cost = float(data["total_cost"])
            avg_cost = float(data["total_cost"] / data["shares"]) if data["shares"] > 0 else 0.0
            position_states.append(PositionState(
                ticker=ticker,
                shares=shares,
                avg_cost=avg_cost,
                cost_basis=total_cost,
            ))

        snapshot = PortfolioSnapshot(cash=float(cash), positions=position_states)

        if prices:
            snapshot.enrich_with_prices(prices)

        return snapshot
