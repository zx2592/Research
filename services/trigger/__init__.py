"""Trigger engine for proactive workflow execution."""

from .dedupe import TriggerStateStore
from .engine import TriggerEngine
from .executor import (
    ResearchWorkflowExecutor,
    WorkflowExecutor,
    build_workflow_executor,
)
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
    "EarningsUpcomingProvider",
    "EarningsUpcomingTriggerRule",
    "PriceMoveProvider",
    "PriceMoveTriggerRule",
    "ResearchWorkflowExecutor",
    "ScheduleProvider",
    "ScheduleSpec",
    "ScheduleTriggerRule",
    "TriggerEngine",
    "TriggerEvent",
    "TriggerStateStore",
    "WorkflowExecutor",
    "WorkflowInvocation",
]
