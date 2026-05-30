from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class TriggerEvent:
    """Normalized event consumed by the trigger engine."""

    event_type: str
    source: str
    occurred_at: datetime
    dedupe_key: str
    payload: Dict[str, Any] = field(default_factory=dict)
    symbol: str | None = None
    severity: str = "info"
    portfolio_scope: str = "global"
    event_id: str | None = None


@dataclass(frozen=True)
class WorkflowInvocation:
    """Concrete workflow action generated from an event."""

    workflow: str
    reason: str
    dedupe_key: str
    ticker: str | None = None
    priority: int = 100
    cooldown_seconds: int = 0
    delivery: Tuple[str, ...] = ("event_log",)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScheduleSpec:
    """Definition of a schedule-driven trigger."""

    name: str
    workflow: str
    reason: str
    hour: int
    minute: int
    cooldown_seconds: int
    ticker: str | None = None
    weekdays: Tuple[int, ...] | None = None
    delivery: Tuple[str, ...] = ("event_log",)

    def is_due(self, now: datetime) -> bool:
        if self.weekdays is not None and now.weekday() not in self.weekdays:
            return False
        return now.hour == self.hour and now.minute == self.minute
