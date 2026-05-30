import os
from datetime import datetime

from core.event_log import EventLog
from services.trigger import (
    DesktopQueueWorkflowExecutor,
    IDETriggerInboxService,
    TriggerEngine,
    TriggerInboxService,
    TriggerStateStore,
    run_trigger_cycle,
)
from services.trigger.rules import EarningsUpcomingTriggerRule, PriceMoveTriggerRule, ScheduleTriggerRule


class TestTriggerMonitor:
    def test_run_trigger_cycle_returns_desktop_notification(self, tmp_dir):
        queue_path = os.path.join(tmp_dir, "desktop_queue.jsonl")
        inbox = TriggerInboxService(
            queue_path=queue_path,
            state_path=os.path.join(tmp_dir, "inbox_state.json"),
        )
        ide = IDETriggerInboxService(inbox)
        engine = TriggerEngine(
            executor=DesktopQueueWorkflowExecutor(queue_path=queue_path, inbox_service=inbox),
            rules=[ScheduleTriggerRule(), PriceMoveTriggerRule(), EarningsUpcomingTriggerRule()],
            event_log=EventLog(log_dir=os.path.join(tmp_dir, "events")),
            state_store=TriggerStateStore(path=os.path.join(tmp_dir, "state.json")),
        )

        messages = run_trigger_cycle(
            executor_mode="desktop",
            now=datetime(2026, 3, 17, 7, 30),
            schedule="morning_scan",
            disable_price=True,
            disable_earnings=True,
            engine=engine,
            ide_inbox=ide,
        )

        assert len(messages) == 1
        assert "[Trigger Inbox]" in messages[0]
        assert "定时任务 morning_scan -> scan" in messages[0]
