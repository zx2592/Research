from __future__ import annotations

from typing import List, Protocol

from core import settings

from .models import TriggerEvent, WorkflowInvocation


class TriggerRule(Protocol):
    def resolve(self, event: TriggerEvent) -> List[WorkflowInvocation]:
        ...


class ScheduleTriggerRule:
    """Map schedule.tick events to workflow invocations."""

    def resolve(self, event: TriggerEvent) -> List[WorkflowInvocation]:
        if event.event_type != "schedule.tick":
            return []
        workflow = event.payload["workflow"]
        return [
            WorkflowInvocation(
                workflow=workflow,
                ticker=event.payload.get("ticker"),
                reason=event.payload["reason"],
                dedupe_key=f"{event.dedupe_key}:{workflow}",
                cooldown_seconds=int(event.payload.get("cooldown_seconds", 0)),
                delivery=tuple(event.payload.get("delivery", ["event_log"])),
                metadata={
                    "event_type": event.event_type,
                    "source": event.source,
                    "schedule_name": event.payload.get("schedule_name"),
                },
            )
        ]


class PriceMoveTriggerRule:
    """Route large price moves into the quick workflow."""

    def __init__(self, cooldown_seconds: int | None = None):
        self.cooldown_seconds = cooldown_seconds if cooldown_seconds is not None else settings.trigger.price_move_cooldown

    def resolve(self, event: TriggerEvent) -> List[WorkflowInvocation]:
        if event.event_type != "price.move":
            return []
        ticker = event.payload["ticker"]
        change_pct = float(event.payload["change_pct"])
        direction = event.payload["direction"]
        return [
            WorkflowInvocation(
                workflow="quick",
                ticker=ticker,
                reason=(
                    f"Run a quick event review for {ticker}. "
                    f"The holding moved {change_pct:+.2f}% and direction is {direction}."
                ),
                dedupe_key=f"price_move:{ticker}:{direction}",
                cooldown_seconds=self.cooldown_seconds,
                metadata={
                    "event_type": event.event_type,
                    "source": event.source,
                    "change_pct": change_pct,
                    "direction": direction,
                },
            )
        ]


class EarningsUpcomingTriggerRule:
    """Route upcoming earnings into the update workflow."""

    def __init__(self, cooldown_seconds: int | None = None):
        self.cooldown_seconds = cooldown_seconds if cooldown_seconds is not None else settings.trigger.earnings_cooldown

    def resolve(self, event: TriggerEvent) -> List[WorkflowInvocation]:
        if event.event_type != "earnings.upcoming":
            return []
        ticker = event.payload["ticker"]
        earnings_date = event.payload["earnings_date"]
        days_left = int(event.payload["days_left"])
        return [
            WorkflowInvocation(
                workflow="update",
                ticker=ticker,
                reason=(
                    f"Run a company update on {ticker}. "
                    f"Earnings are scheduled for {earnings_date} ({days_left} days away)."
                ),
                dedupe_key=f"earnings_upcoming:{ticker}",
                cooldown_seconds=self.cooldown_seconds,
                metadata={
                    "event_type": event.event_type,
                    "source": event.source,
                    "earnings_date": earnings_date,
                    "days_left": days_left,
                },
            )
        ]
