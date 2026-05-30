from __future__ import annotations

from typing import Iterable, List

from core.event_log import Event, EventLog

from .dedupe import TriggerStateStore
from .models import TriggerEvent, WorkflowInvocation


class TriggerEngine:
    """Event-driven workflow router with cooldown and audit logging."""

    def __init__(
        self,
        executor,
        rules: Iterable,
        event_log: EventLog | None = None,
        state_store: TriggerStateStore | None = None,
    ):
        self.executor = executor
        self.rules = list(rules)
        self.event_log = event_log or EventLog()
        self.state_store = state_store or TriggerStateStore()

    def collect_invocations(self, event: TriggerEvent) -> List[WorkflowInvocation]:
        invocations: List[WorkflowInvocation] = []
        for rule in self.rules:
            invocations.extend(rule.resolve(event))
        return sorted(invocations, key=lambda item: item.priority)

    def process_event(self, event: TriggerEvent) -> List[dict]:
        self.event_log.emit(
            Event(
                event_type="trigger.received",
                source="trigger.engine",
                payload={
                    "trigger_event_type": event.event_type,
                    "source": event.source,
                    "dedupe_key": event.dedupe_key,
                    "symbol": event.symbol,
                    "payload": event.payload,
                },
            )
        )

        results: List[dict] = []
        for invocation in self.collect_invocations(event):
            if not self.state_store.should_fire(
                invocation.dedupe_key,
                now=event.occurred_at,
                cooldown_seconds=invocation.cooldown_seconds,
            ):
                self.event_log.emit(
                    Event(
                        event_type="trigger.skipped",
                        source="trigger.engine",
                        payload={
                            "workflow": invocation.workflow,
                            "dedupe_key": invocation.dedupe_key,
                            "reason": "cooldown",
                        },
                    )
                )
                continue

            self.event_log.emit(
                Event(
                    event_type="trigger.fired",
                    source="trigger.engine",
                    payload={
                        "workflow": invocation.workflow,
                        "ticker": invocation.ticker,
                        "reason": invocation.reason,
                        "dedupe_key": invocation.dedupe_key,
                        "metadata": invocation.metadata,
                    },
                )
            )

            try:
                result = self.executor.invoke(invocation)
                self.state_store.mark_fired(invocation.dedupe_key, event.occurred_at)
                self.event_log.emit(
                    Event(
                        event_type="trigger.completed",
                        source="trigger.engine",
                        payload={
                            "workflow": invocation.workflow,
                            "ticker": invocation.ticker,
                            "dedupe_key": invocation.dedupe_key,
                        },
                    )
                )
                results.append(
                    {
                        "status": "completed",
                        "workflow": invocation.workflow,
                        "ticker": invocation.ticker,
                        "result": result,
                    }
                )
            except Exception as exc:
                self.event_log.emit(
                    Event(
                        event_type="trigger.failed",
                        source="trigger.engine",
                        payload={
                            "workflow": invocation.workflow,
                            "ticker": invocation.ticker,
                            "dedupe_key": invocation.dedupe_key,
                            "error": str(exc),
                        },
                    )
                )
                raise

        return results
