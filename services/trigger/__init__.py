"""Trigger engine for proactive workflow execution."""

from .dedupe import TriggerStateStore
from .engine import TriggerEngine
from .executor import (
    DesktopQueueWorkflowExecutor,
    ResearchWorkflowExecutor,
    WorkflowExecutor,
    build_workflow_executor,
)
from .inbox import TriggerInboxService
from .ide_dialog_inbox import IDETriggerInboxService
from .monitor import DEFAULT_SCHEDULES, build_monitor_engine, run_trigger_cycle, serve_trigger_loop
from .models import ScheduleSpec, TriggerEvent, WorkflowInvocation
from .provider import EarningsUpcomingProvider, PriceMoveProvider, ScheduleProvider
from .rules import EarningsUpcomingTriggerRule, PriceMoveTriggerRule, ScheduleTriggerRule

__all__ = [
    "DEFAULT_SCHEDULES",
    "build_monitor_engine",
    "run_trigger_cycle",
    "serve_trigger_loop",
    "build_workflow_executor",
    "DesktopQueueWorkflowExecutor",
    "EarningsUpcomingProvider",
    "EarningsUpcomingTriggerRule",
    "IDETriggerInboxService",
    "PriceMoveProvider",
    "PriceMoveTriggerRule",
    "ResearchWorkflowExecutor",
    "ScheduleProvider",
    "ScheduleSpec",
    "ScheduleTriggerRule",
    "TriggerInboxService",
    "TriggerEngine",
    "TriggerEvent",
    "TriggerStateStore",
    "WorkflowExecutor",
    "WorkflowInvocation",
]
