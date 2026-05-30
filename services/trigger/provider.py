from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Callable, Dict, Iterable, List

from .models import ScheduleSpec, TriggerEvent


class ScheduleProvider:
    """Generates schedule.tick events when specs are due."""

    def __init__(self, schedules: Iterable[ScheduleSpec]):
        self.schedules = list(schedules)

    def collect(self, now: datetime | None = None) -> List[TriggerEvent]:
        now = now or datetime.now()
        events: List[TriggerEvent] = []
        for spec in self.schedules:
            if not spec.is_due(now):
                continue
            dedupe_suffix = now.strftime("%Y%m%d%H%M")
            events.append(
                TriggerEvent(
                    event_type="schedule.tick",
                    source="schedule_provider",
                    occurred_at=now,
                    dedupe_key=f"schedule:{spec.name}:{dedupe_suffix}",
                    payload={
                        "schedule_name": spec.name,
                        "workflow": spec.workflow,
                        "reason": spec.reason,
                        "ticker": spec.ticker,
                        "cooldown_seconds": spec.cooldown_seconds,
                        "delivery": list(spec.delivery),
                    },
                    symbol=spec.ticker,
                )
            )
        return events


def _load_holdings_raw(holdings_path: str) -> dict:
    """Read the full holdings.json."""
    if not os.path.exists(holdings_path):
        return {}
    with open(holdings_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_holding_tickers(holdings_path: str) -> Dict[str, dict]:
    """Read holdings.json and return the raw ticker mapping."""
    return _load_holdings_raw(holdings_path).get("tickers", {})


class PriceMoveProvider:
    """Generate price_move events for holdings with large daily changes."""

    def __init__(
        self,
        fetch_prices: Callable[[], List[dict]],
        threshold_pct: float = 3.5,
    ):
        self.fetch_prices = fetch_prices
        self.threshold_pct = threshold_pct

    def collect(self, now: datetime | None = None) -> List[TriggerEvent]:
        now = now or datetime.now()
        events: List[TriggerEvent] = []
        for asset in self.fetch_prices():
            change = float(asset.get("change", 0.0) or 0.0)
            if abs(change) < self.threshold_pct:
                continue
            ticker = asset.get("ticker")
            direction = "up" if change > 0 else "down"
            events.append(
                TriggerEvent(
                    event_type="price.move",
                    source="price_move_provider",
                    occurred_at=now,
                    dedupe_key=f"price_move:{ticker}:{direction}",
                    payload={
                        "ticker": ticker,
                        "name": asset.get("name", ticker),
                        "change_pct": change,
                        "price": asset.get("price"),
                        "threshold_pct": self.threshold_pct,
                        "direction": direction,
                    },
                    symbol=ticker,
                    severity="high" if abs(change) >= self.threshold_pct * 1.5 else "medium",
                    portfolio_scope="holdings",
                )
            )
        return events


class EarningsUpcomingProvider:
    """Generate earnings.upcoming events for holdings with near-term earnings dates."""

    def __init__(
        self,
        holdings_path: str,
        earnings_fetcher: Callable[[str], datetime | None],
        lookahead_days: int = 7,
    ):
        self.holdings_path = holdings_path
        self.earnings_fetcher = earnings_fetcher
        self.lookahead_days = lookahead_days

    def collect(self, now: datetime | None = None) -> List[TriggerEvent]:
        now = now or datetime.now()
        deadline = now + timedelta(days=self.lookahead_days)
        holdings_data = _load_holdings_raw(self.holdings_path)
        tickers = holdings_data.get("tickers", {})
        skip = set(holdings_data.get("no_earnings_tickers", []))
        events: List[TriggerEvent] = []

        for ticker in tickers:
            if ticker in skip:
                continue
            earnings_dt = self.earnings_fetcher(ticker)
            if earnings_dt is None:
                continue
            if earnings_dt < now or earnings_dt > deadline:
                continue
            days_left = max(0, (earnings_dt - now).days)
            events.append(
                TriggerEvent(
                    event_type="earnings.upcoming",
                    source="earnings_provider",
                    occurred_at=now,
                    dedupe_key=f"earnings_upcoming:{ticker}",
                    payload={
                        "ticker": ticker,
                        "earnings_date": earnings_dt.strftime("%Y-%m-%d"),
                        "days_left": days_left,
                        "lookahead_days": self.lookahead_days,
                    },
                    symbol=ticker,
                    severity="high" if days_left <= 2 else "medium",
                    portfolio_scope="holdings",
                )
            )
        return events
