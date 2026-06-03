import os
from datetime import datetime

from core.event_log import EventLog
from services.trigger import (
    TriggerEngine,
    TriggerStateStore,
    run_trigger_cycle,
)
from services.trigger.rules import EarningsUpcomingTriggerRule, PriceMoveTriggerRule, ScheduleTriggerRule


class _StubExecutor:
    def __init__(self):
        self.calls = []

    def invoke(self, invocation):
        self.calls.append(invocation)
        return {"ok": True, "workflow": invocation.workflow, "ticker": invocation.ticker}


class TestTriggerMonitor:
    def test_run_trigger_cycle_runs_workflow_directly(self, tmp_dir):
        executor = _StubExecutor()
        engine = TriggerEngine(
            executor=executor,
            rules=[ScheduleTriggerRule(), PriceMoveTriggerRule(), EarningsUpcomingTriggerRule()],
            event_log=EventLog(log_dir=os.path.join(tmp_dir, "events")),
            state_store=TriggerStateStore(path=os.path.join(tmp_dir, "state.json")),
        )

        messages = run_trigger_cycle(
            now=datetime(2026, 3, 17, 7, 30),
            schedule="morning_scan",
            disable_price=True,
            disable_earnings=True,
            engine=engine,
        )

        assert len(messages) == 1
        assert messages[0] == "Triggered scan"
        assert executor.calls[0].workflow == "scan"
