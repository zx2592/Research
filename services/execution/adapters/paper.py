"""
PaperAdapter — 模拟交易适配器

Simulates trade execution without touching a real broker.
Fills are executed at the provided price.
"""
from datetime import datetime, timezone
from typing import Any, Dict

from core.artifacts.schemas import OrderIntent
from services.portfolio.events import FillEvent
from services.portfolio.ledger import PortfolioLedger


class PaperAdapter:
    """Simulates order execution; fills at given price."""

    def __init__(self, ledger: PortfolioLedger):
        self.ledger = ledger

    def execute(self, intent: OrderIntent, prices: Dict[str, float]) -> Dict[str, Any]:
        """
        Simulate a fill and record it into the ledger.
        Returns a fill receipt dict.
        """
        price = prices.get(intent.ticker, 0.0)
        commission = 0.0  # paper trading: no commission

        fill = FillEvent(
            ticker=intent.ticker,
            side=intent.side,
            quantity=float(intent.quantity),
            price=price,
            commission=commission,
            account="paper",
            order_intent_id=intent.intent_id,
        )
        self.ledger.emit(fill)

        return {
            "ticker": intent.ticker,
            "side": intent.side,
            "quantity": float(intent.quantity),
            "price": price,
            "commission": commission,
            "fill_id": fill.event_id,
            "timestamp": fill.timestamp.isoformat(),
            "status": "filled",
            "mode": "paper",
        }
