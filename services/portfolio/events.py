"""
Portfolio Events — 组合事件模型

Event sourcing: every position change comes from an event.
All events are append-only and can replay to any point in time.

Fix: use explicit __init__ to avoid Python dataclass inheritance
ordering issues (non-default fields after default fields).
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class EventType(str, Enum):
    FILL        = "fill"
    CASH_FLOW   = "cash_flow"
    SPLIT       = "split"
    DIVIDEND    = "dividend"
    FX_RATE     = "fx_rate"


class PortfolioEvent:
    """Base class for all portfolio events."""

    def __init__(self, event_type: EventType):
        self.event_type: EventType = event_type
        self.event_id: str = uuid.uuid4().hex[:16]
        self.timestamp: datetime = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
        }


class FillEvent(PortfolioEvent):
    """成交事件 — records a trade execution."""

    def __init__(
        self,
        ticker: str,
        side: str,
        quantity: float,
        price: float,
        commission: float,
        account: str,
        order_intent_id: Optional[str] = None,
    ):
        super().__init__(EventType.FILL)
        self.ticker = ticker
        self.side = side                    # "buy" / "sell"
        self.quantity = quantity
        self.price = price
        self.commission = commission
        self.account = account
        self.order_intent_id = order_intent_id

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "ticker": self.ticker,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "commission": self.commission,
            "account": self.account,
            "order_intent_id": self.order_intent_id,
        })
        return d


class CashFlowEvent(PortfolioEvent):
    """现金流事件 — deposit, withdrawal, dividend, interest, option premium."""

    def __init__(
        self,
        amount: float,
        currency: str = "USD",
        category: str = "deposit",
    ):
        super().__init__(EventType.CASH_FLOW)
        self.amount = amount
        self.currency = currency
        self.category = category    # "deposit" / "withdrawal" / "dividend" / ...

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "amount": self.amount,
            "currency": self.currency,
            "category": self.category,
        })
        return d


class SplitEvent(PortfolioEvent):
    """股票拆分事件."""

    def __init__(self, ticker: str, ratio: float):
        super().__init__(EventType.SPLIT)
        self.ticker = ticker
        self.ratio = ratio  # e.g. 2.0 for 2-for-1 split

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({"ticker": self.ticker, "ratio": self.ratio})
        return d
